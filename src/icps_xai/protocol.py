"""Confirmatory experiment jobs, manifests, and deterministic aggregation."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import statistics
import subprocess
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .baselines import feature_counterfactual
from .campaign import CampaignValidator, reference_campaign
from .counterfactual import CounterfactualSearch, RandomValidSearch, SearchConfig
from .domain import AttackStage, Campaign, CounterfactualResult
from .experiment import train_responder
from .feasibility import PhysicalFeasibilityChecker
from .metrics import maximum_band_deviation
from .simulation import ICPSSimulator, SimulationConfig


SCHEMA_VERSION = "1.0"
METHODS = ("feature_cf", "random_valid", "cyber_only", "proposed")


def validate_config(config: dict[str, Any]) -> None:
    required = {
        "protocol_name",
        "training_episodes",
        "evaluation_policy_seeds",
        "horizon",
        "audit_lead",
        "search_depth",
        "beam_width",
        "search_evaluation_budget",
        "minimum_impact_gain",
    }
    missing = sorted(required - set(config))
    if missing:
        raise ValueError(f"configuration lacks keys: {missing}")
    seeds = [int(seed) for seed in config["evaluation_policy_seeds"]]
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("evaluation_policy_seeds must be nonempty and unique")
    positive_integer_keys = (
        "training_episodes",
        "horizon",
        "audit_lead",
        "search_depth",
        "beam_width",
        "search_evaluation_budget",
    )
    for key in positive_integer_keys:
        if int(config[key]) <= 0:
            raise ValueError(f"{key} must be positive")
    if int(config["horizon"]) < 90:
        raise ValueError("horizon is too short for the commissioned scenarios")
    if float(config["minimum_impact_gain"]) < 0.0:
        raise ValueError("minimum_impact_gain must be nonnegative")


def _config_hash(config: dict[str, Any]) -> str:
    blob = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _git_commit(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def _git_dirty(root: Path) -> bool | None:
    try:
        output = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, text=True, stderr=subprocess.DEVNULL
        )
        return bool(output.strip())
    except (OSError, subprocess.CalledProcessError):
        return None


def scenario_suite() -> tuple[Campaign, ...]:
    reference = reference_campaign(name="S0_reference", impact_magnitude=1.12)
    shifted = reference_campaign(name="S1_shifted", offset=-2, impact_magnitude=1.00)
    pump = reference_campaign(name="S2_transfer_pump", offset=1, impact_magnitude=1.18)
    pump_events = tuple(
        event.edited(asset="transfer_pump")
        if event.stage is AttackStage.ACTUATOR_OVERRIDE
        else event
        for event in pump.events
    )
    lower_visibility = reference_campaign(name="S3_lower_visibility", impact_magnitude=1.08)
    lower_events = tuple(
        event
        if event.stage is AttackStage.ACTUATOR_OVERRIDE
        else event.edited(visibility=event.visibility * 0.78)
        for event in lower_visibility.events
    )
    return reference, shifted, Campaign(pump.name, pump_events), Campaign(lower_visibility.name, lower_events)


def _impact_time(campaign: Campaign) -> int:
    return next(event.time for event in campaign.events if event.stage is AttackStage.ACTUATOR_OVERRIDE)


def _campaign_result(
    method: str,
    result: CounterfactualResult | None,
    policy: Any,
    horizon: int,
    transfer_seed: int,
    audit_lead: int,
    runtime: float,
    evaluations: int,
) -> dict[str, Any]:
    if result is None:
        return {
            "method": method,
            "status": "not_found",
            "decision_weakened": False,
            "cyber_feasible": None,
            "physical_executable": None,
            "impact_valid": False,
            "evaluations": evaluations,
            "runtime_seconds": runtime,
        }
    checker = PhysicalFeasibilityChecker(horizon, seeds=(transfer_seed, transfer_seed + 17))
    feasible = checker.check(result.counterfactual_campaign, policy)
    impact_time = _impact_time(result.counterfactual_campaign)
    transfer = ICPSSimulator(SimulationConfig(horizon=horizon, high_fidelity=True))
    factual_trace = transfer.run(result.factual_campaign, policy.clone(), seed=transfer_seed)
    candidate_trace = transfer.run(result.counterfactual_campaign, policy.clone(), seed=transfer_seed)
    audit_time = impact_time - audit_lead
    transfer_factual_action = factual_trace.steps[audit_time].action
    transfer_action = candidate_trace.steps[audit_time].action
    transfer_gain = maximum_band_deviation(candidate_trace, impact_time) - maximum_band_deviation(
        factual_trace, impact_time
    )
    return {
        "method": method,
        "status": "found",
        "decision_weakened": result.decision_weakened,
        "factual_action": result.factual_action.name,
        "counterfactual_action": result.counterfactual_action.name,
        "cyber_feasible": feasible.cyber_valid,
        "physical_executable": feasible.valid,
        "impact_valid": result.impact_gain > 0.0,
        "impact_gain": result.impact_gain,
        "edit_cost": result.edit_cost,
        "edit_count": len(result.edits),
        "evaluations": result.evaluations,
        "runtime_seconds": runtime,
        "transfer_decision_weakened": transfer_action < transfer_factual_action,
        "transfer_impact_gain": transfer_gain,
        "edits": [asdict(edit) for edit in result.edits],
    }


def run_job(config: dict[str, Any], root: Path, job_index: int, output_dir: Path) -> dict[str, Any]:
    """Run one deterministic policy seed over all held-out scenarios."""

    validate_config(config)
    seeds = [int(value) for value in config["evaluation_policy_seeds"]]
    if not 0 <= job_index < len(seeds):
        raise ValueError(f"job index {job_index} outside 0..{len(seeds) - 1}")
    seed = seeds[job_index]
    horizon = int(config["horizon"])
    audit_lead = int(config["audit_lead"])
    budget = int(config["search_evaluation_budget"])
    common = dict(
        depth=int(config["search_depth"]),
        beam_width=int(config["beam_width"]),
        audit_lead=audit_lead,
        minimum_impact_gain=float(config["minimum_impact_gain"]),
        max_evaluations=budget,
    )
    learner = train_responder(seed, int(config["training_episodes"]), horizon)
    policy = learner.freeze()
    policy_digest = policy.digest()
    simulator = ICPSSimulator(SimulationConfig(horizon=horizon))
    validator = CampaignValidator()
    records: list[dict[str, Any]] = []

    for scenario_index, factual in enumerate(scenario_suite()):
        validity = validator.validate(factual, horizon)
        if not validity.valid:
            raise RuntimeError(f"invalid commissioned scenario {factual.name}: {validity.errors}")
        impact_time = _impact_time(factual)
        audit_time = impact_time - audit_lead
        scenario_seed = seed + 500 + scenario_index
        factual_trace = simulator.run(factual, policy.clone(), seed=scenario_seed)
        search_options = dict(common, seed=scenario_seed)

        started = time.monotonic()
        feature = feature_counterfactual(factual_trace, policy, audit_time)
        feature_runtime = time.monotonic() - started
        records.append(
            {
                "method": "feature_cf",
                "status": "found" if feature else "not_found",
                "decision_weakened": bool(feature and feature.decision_weakened),
                "factual_action": (
                    feature.factual_action.name
                    if feature
                    else factual_trace.steps[audit_time].action.name
                ),
                "counterfactual_action": feature.counterfactual_action.name if feature else None,
                "cyber_feasible": False if feature else None,
                "physical_executable": False if feature else None,
                "impact_valid": None,
                "edit_cost": (1.0 - feature.scale) * feature.changed_values if feature else None,
                "edit_count": feature.changed_values if feature else None,
                "evaluations": feature.evaluations if feature else 20,
                "runtime_seconds": feature_runtime,
                "transfer_decision_weakened": None,
                "transfer_impact_gain": None,
            }
        )

        searches = (
            (
                "random_valid",
                RandomValidSearch(simulator, validator, SearchConfig(**search_options, require_impact_gain=True)),
            ),
            (
                "cyber_only",
                CounterfactualSearch(simulator, validator, SearchConfig(**search_options, require_impact_gain=False)),
            ),
            (
                "proposed",
                CounterfactualSearch(simulator, validator, SearchConfig(**search_options, require_impact_gain=True)),
            ),
        )
        for method, search in searches:
            started = time.monotonic()
            result = search.search(factual, policy.clone())
            runtime = time.monotonic() - started
            records.append(
                _campaign_result(
                    method,
                    result,
                    policy,
                    horizon,
                    seed + 700 + scenario_index,
                    audit_lead,
                    runtime,
                    search.last_evaluations,
                )
            )
        for record in records[-len(METHODS) :]:
            record.update(
                {
                    "job_index": job_index,
                    "policy_seed": seed,
                    "scenario_index": scenario_index,
                    "scenario": factual.name,
                }
            )

    if policy.digest() != policy_digest:
        raise RuntimeError("the frozen policy changed during explanation")
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "kind": "counterfactual_job",
        "config_hash": _config_hash(config),
        "git_commit": _git_commit(root),
        "git_dirty": _git_dirty(root),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "job_index": job_index,
        "policy_seed": seed,
        "policy_digest": policy_digest,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "records": records,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"job_{job_index:04d}.json"
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, destination)
    return artifact


def aggregate_jobs(config: dict[str, Any], input_dir: Path, destination: Path) -> dict[str, Any]:
    validate_config(config)
    expected_hash = _config_hash(config)
    jobs = []
    seen: set[int] = set()
    for path in sorted(input_dir.glob("job_*.json")):
        job = json.loads(path.read_text(encoding="utf-8"))
        if job.get("schema_version") != SCHEMA_VERSION or job.get("config_hash") != expected_hash:
            raise ValueError(f"incompatible job artifact: {path}")
        index = int(job["job_index"])
        if not 0 <= index < len(config["evaluation_policy_seeds"]):
            raise ValueError(f"job index outside configured range in {path}")
        if index in seen:
            raise ValueError(f"duplicate job index {index}")
        seen.add(index)
        if int(job.get("policy_seed", -1)) != int(config["evaluation_policy_seeds"][index]):
            raise ValueError(f"policy seed does not match job index in {path}")
        expected_pairs = {
            (method, scenario.name) for method in METHODS for scenario in scenario_suite()
        }
        actual_pairs = {(row.get("method"), row.get("scenario")) for row in job.get("records", [])}
        if actual_pairs != expected_pairs or len(job.get("records", [])) != len(expected_pairs):
            raise ValueError(f"incomplete or duplicate method/scenario grid in {path}")
        jobs.append(job)
    expected = set(range(len(config["evaluation_policy_seeds"])))
    if seen != expected:
        raise ValueError(f"missing job indices: {sorted(expected - seen)}")
    commits = {job.get("git_commit") for job in jobs}
    if len(commits) != 1:
        raise ValueError(f"job artifacts come from different commits: {sorted(commits)}")
    if str(config["protocol_name"]).startswith(
        "icps_counterfactual_red_teaming_confirmatory"
    ):
        if any(job.get("git_dirty") is True for job in jobs):
            raise ValueError("confirmatory artifacts were produced from a dirty worktree")
    records = [record for job in jobs for record in job["records"]]
    summary: dict[str, Any] = {}
    for method in METHODS:
        rows = [row for row in records if row["method"] == method]
        found = [row for row in rows if row["status"] == "found"]
        valid = [
            row
            for row in found
            if row.get("decision_weakened")
            and row.get("cyber_feasible") is True
            and row.get("physical_executable") is True
            and row.get("impact_valid") is True
        ]
        gains = [float(row["impact_gain"]) for row in valid if row.get("impact_gain") is not None]
        costs = [float(row["edit_cost"]) for row in found if row.get("edit_cost") is not None]
        runtimes = [float(row["runtime_seconds"]) for row in rows]
        evaluations = [float(row["evaluations"]) for row in rows]
        summary[method] = {
            "runs": len(rows),
            "found": len(found),
            "valid": len(valid),
            "found_rate": len(found) / max(1, len(rows)),
            "target_valid_rate": sum(row.get("decision_weakened") is True for row in rows) / max(1, len(rows)),
            "cyber_feasible_rate": sum(
                row.get("cyber_feasible") is True for row in found
            ) / max(1, len(found)),
            "physical_executable_rate": sum(
                row.get("physical_executable") is True for row in found
            ) / max(1, len(found)),
            "impact_valid_rate": sum(
                row.get("impact_valid") is True for row in found
            ) / max(1, len(found)),
            "valid_rate": len(valid) / max(1, len(rows)),
            "median_impact_gain": statistics.median(gains) if gains else None,
            "impact_gain_iqr": _iqr(gains),
            "median_edit_cost": statistics.median(costs) if costs else None,
            "edit_cost_iqr": _iqr(costs),
            "median_evaluations": statistics.median(evaluations),
            "median_runtime_seconds": statistics.median(runtimes),
            "transfer_valid_rate": sum(
                row.get("transfer_decision_weakened") is True
                and (row.get("transfer_impact_gain") or 0.0) > 0.0
                for row in found
            ) / max(1, len(found)),
        }
    summary["paired_proposed_minus_random_valid"] = _paired_validity_difference(
        records, "proposed", "random_valid"
    )
    summary["paired_proposed_minus_cyber_only"] = _paired_validity_difference(
        records, "proposed", "cyber_only"
    )
    aggregate = {
        "schema_version": SCHEMA_VERSION,
        "kind": "counterfactual_aggregate",
        "config_hash": expected_hash,
        "jobs": len(jobs),
        "records": records,
        "summary": summary,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_aggregate_csv(destination.with_suffix(".csv"), summary)
    return aggregate


def _iqr(values: list[float]) -> list[float] | None:
    if len(values) < 2:
        return None
    quartiles = statistics.quantiles(values, n=4, method="inclusive")
    return [quartiles[0], quartiles[2]]


def _paired_validity_difference(
    records: list[dict[str, Any]], left: str, right: str
) -> dict[str, float | list[float]]:
    keyed = {(row["job_index"], row["scenario_index"], row["method"]): row for row in records}
    differences: list[float] = []
    units = sorted({(row["job_index"], row["scenario_index"]) for row in records})
    for job_index, scenario_index in units:
        pair = []
        for method in (left, right):
            row = keyed[(job_index, scenario_index, method)]
            pair.append(
                float(
                    row.get("decision_weakened") is True
                    and row.get("cyber_feasible") is True
                    and row.get("physical_executable") is True
                    and row.get("impact_valid") is True
                )
            )
        differences.append(pair[0] - pair[1])
    observed = statistics.mean(differences) if differences else 0.0
    # Deterministic paired bootstrap over campaign-policy units.
    import random

    rng = random.Random(20270908)
    samples = []
    if differences:
        for _ in range(5000):
            samples.append(statistics.mean(rng.choice(differences) for _ in differences))
        samples.sort()
        low = samples[int(0.025 * (len(samples) - 1))]
        high = samples[int(0.975 * (len(samples) - 1))]
    else:
        low = high = 0.0
    return {"mean_difference": observed, "bootstrap_95_ci": [low, high]}


def _write_aggregate_csv(path: Path, summary: dict[str, Any]) -> None:
    import csv

    fields = (
        "method",
        "runs",
        "found_rate",
        "target_valid_rate",
        "cyber_feasible_rate",
        "physical_executable_rate",
        "impact_valid_rate",
        "valid_rate",
        "median_impact_gain",
        "median_edit_cost",
        "median_evaluations",
        "median_runtime_seconds",
        "transfer_valid_rate",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for method in METHODS:
            writer.writerow({"method": method, **summary[method]})


def write_confirmatory_latex(path: Path, summary: dict[str, Any]) -> None:
    """Create the paper table only from a successfully aggregated result."""

    labels = {
        "feature_cf": "Feature-CF",
        "random_valid": "Random-valid",
        "cyber_only": "Cyber-CF",
        "proposed": "Cyber-physical CF",
    }
    lines = [
        "\\begin{table*}[t]",
        "\\caption{Confirmatory counterfactual comparison across all policy--campaign units.}",
        "\\label{tab:confirmatory}",
        "\\centering",
        "\\begin{tabular}{lrrrrrr}",
        "\\toprule",
        "Method & Target (\\%) & Cyber (\\%) & Physical (\\%) & Valid (\\%) & Impact gain & Transfer (\\%) \\\\",
        "\\midrule",
    ]
    for method in METHODS:
        row = summary[method]
        gain = row["median_impact_gain"]
        gain_text = "--" if gain is None else f"{float(gain):.4f}"
        lines.append(
            f"{labels[method]} & "
            f"{100.0 * float(row['target_valid_rate']):.1f} & "
            f"{100.0 * float(row['cyber_feasible_rate']):.1f} & "
            f"{100.0 * float(row['physical_executable_rate']):.1f} & "
            f"{100.0 * float(row['valid_rate']):.1f} & "
            f"{gain_text} & "
            f"{100.0 * float(row['transfer_valid_rate']):.1f} \\\\"
        )
    lines.extend(("\\bottomrule", "\\end{tabular}", "\\end{table*}", ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
