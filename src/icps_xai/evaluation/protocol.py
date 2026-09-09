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

from ..core.campaign import CampaignValidator, reference_campaign
from ..core.domain import AttackStage, Campaign, CounterfactualResult, ResponseAction
from ..explainers.baselines import feature_counterfactual
from ..explainers.counterfactual import CounterfactualSearch, RandomValidSearch, SearchConfig
from ..simulators.simulation import ICPSSimulator, SimulationConfig
from .experiment import train_responder
from .feasibility import PhysicalFeasibilityChecker
from .metrics import maximum_band_deviation


SCHEMA_VERSION = "1.1"
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
        "responder_learning_rate",
        "responder_discount",
        "response_costs",
        "switching_cost",
        "seed_offsets",
        "bootstrap_seed",
        "scenarios",
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
    learning_rate = float(config["responder_learning_rate"])
    discount = float(config["responder_discount"])
    if not 0.0 < learning_rate <= 1.0:
        raise ValueError("responder_learning_rate must be in (0,1]")
    if not 0.0 <= discount < 1.0:
        raise ValueError("responder_discount must be in [0,1)")
    costs = [float(value) for value in config["response_costs"]]
    if len(costs) != len(tuple(ResponseAction)):
        raise ValueError("response_costs must contain one value per response action")
    if any(value < 0.0 for value in costs):
        raise ValueError("response_costs must be nonnegative")
    if costs[0] != 0.0 or costs != sorted(costs):
        raise ValueError("response_costs must start at zero and increase with response strength")
    if float(config["switching_cost"]) < 0.0:
        raise ValueError("switching_cost must be nonnegative")
    offsets = config["seed_offsets"]
    if not isinstance(offsets, dict) or set(offsets) != {"training", "scenario", "transfer"}:
        raise ValueError("seed_offsets must define training, scenario, and transfer")
    if any(int(value) <= 0 for value in offsets.values()):
        raise ValueError("seed offsets must be positive")
    if len({int(value) for value in offsets.values()}) != 3:
        raise ValueError("seed offsets must be distinct")
    if int(config["bootstrap_seed"]) < 0:
        raise ValueError("bootstrap_seed must be nonnegative")
    scenarios = config["scenarios"]
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenarios must be a nonempty list")
    if any(not isinstance(item, dict) for item in scenarios):
        raise ValueError("each scenario must be an object")
    scenario_keys = {
        "name",
        "offset",
        "impact_magnitude",
        "actuator",
        "precursor_visibility_scale",
    }
    for item in scenarios:
        missing_scenario_keys = scenario_keys - set(item)
        if missing_scenario_keys:
            raise ValueError(f"scenario lacks keys: {sorted(missing_scenario_keys)}")
    names = [str(item.get("name", "")) for item in scenarios]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise ValueError("scenario names must be nonempty and unique")
    for specification, scenario in zip(scenarios, scenario_suite(config)):
        magnitude = float(specification["impact_magnitude"])
        visibility_scale = float(specification["precursor_visibility_scale"])
        if not 0.0 < magnitude <= 1.5:
            raise ValueError(f"scenario {scenario.name} impact_magnitude must be in (0,1.5]")
        if not 0.0 < visibility_scale <= 1.0:
            raise ValueError(
                f"scenario {scenario.name} precursor_visibility_scale must be in (0,1]"
            )
        result = CampaignValidator().validate(scenario, int(config["horizon"]))
        if not result.valid:
            raise ValueError(f"invalid configured scenario {scenario.name}: {result.errors}")
        if int(config["audit_lead"]) > _impact_time(scenario):
            raise ValueError(f"audit_lead places {scenario.name} before the start of the trace")


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


def scenario_suite(config: dict[str, Any]) -> tuple[Campaign, ...]:
    scenarios: list[Campaign] = []
    for spec in config["scenarios"]:
        campaign = reference_campaign(
            name=str(spec["name"]),
            offset=int(spec["offset"]),
            impact_magnitude=float(spec["impact_magnitude"]),
        )
        actuator = str(spec["actuator"])
        visibility_scale = float(spec["precursor_visibility_scale"])
        events = tuple(
            event.edited(asset=actuator)
            if event.stage is AttackStage.ACTUATOR_OVERRIDE
            else event.edited(visibility=event.visibility * visibility_scale)
            for event in campaign.events
        )
        scenarios.append(Campaign(campaign.name, events))
    return tuple(scenarios)


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
    generated_candidates: int,
    invalid_candidates: int,
    duplicate_candidates: int,
    factual_action: ResponseAction,
    minimum_impact_gain: float,
    response_costs: tuple[float, float, float, float],
    switching_cost: float,
) -> dict[str, Any]:
    if result is None:
        return {
            "method": method,
            "status": "not_found",
            "decision_weakened": False,
            "factual_action": factual_action.name,
            "counterfactual_action": None,
            "cyber_feasible": None,
            "physical_executable": None,
            "impact_valid": False,
            "impact_gain": None,
            "edit_cost": None,
            "edit_count": None,
            "evaluations": evaluations,
            "generated_candidates": generated_candidates,
            "invalid_candidates": invalid_candidates,
            "duplicate_candidates": duplicate_candidates,
            "runtime_seconds": runtime,
            "transfer_decision_weakened": None,
            "transfer_impact_gain": None,
            "edits": [],
        }
    if result.factual_action is not factual_action:
        raise RuntimeError("search and commissioned factual traces disagree at the audit instant")
    checker = PhysicalFeasibilityChecker(
        horizon,
        seeds=(transfer_seed, transfer_seed + 17),
        response_costs=response_costs,
        switching_cost=switching_cost,
    )
    feasible = checker.check(result.counterfactual_campaign, policy)
    impact_time = _impact_time(result.counterfactual_campaign)
    transfer = ICPSSimulator(
        SimulationConfig(
            horizon=horizon,
            high_fidelity=True,
            response_costs=response_costs,
            switching_cost=switching_cost,
        )
    )
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
        "impact_valid": result.impact_gain >= minimum_impact_gain,
        "impact_gain": result.impact_gain,
        "edit_cost": result.edit_cost,
        "edit_count": len(result.edits),
        "evaluations": result.evaluations,
        "generated_candidates": generated_candidates,
        "invalid_candidates": invalid_candidates,
        "duplicate_candidates": duplicate_candidates,
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
    response_costs = tuple(float(value) for value in config["response_costs"])
    seed_offsets = {key: int(value) for key, value in config["seed_offsets"].items()}
    common = dict(
        depth=int(config["search_depth"]),
        beam_width=int(config["beam_width"]),
        audit_lead=audit_lead,
        minimum_impact_gain=float(config["minimum_impact_gain"]),
        max_evaluations=budget,
    )
    learner = train_responder(
        seed,
        int(config["training_episodes"]),
        horizon,
        learning_rate=float(config["responder_learning_rate"]),
        discount=float(config["responder_discount"]),
        response_costs=response_costs,  # type: ignore[arg-type]
        switching_cost=float(config["switching_cost"]),
        training_seed_offset=seed_offsets["training"],
    )
    policy = learner.freeze()
    policy_digest = policy.digest()
    simulator = ICPSSimulator(
        SimulationConfig(
            horizon=horizon,
            response_costs=response_costs,  # type: ignore[arg-type]
            switching_cost=float(config["switching_cost"]),
        )
    )
    validator = CampaignValidator()
    records: list[dict[str, Any]] = []

    for scenario_index, factual in enumerate(scenario_suite(config)):
        validity = validator.validate(factual, horizon)
        if not validity.valid:
            raise RuntimeError(f"invalid commissioned scenario {factual.name}: {validity.errors}")
        impact_time = _impact_time(factual)
        audit_time = impact_time - audit_lead
        scenario_seed = seed + seed_offsets["scenario"] + scenario_index
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
                "impact_gain": None,
                "edit_cost": (1.0 - feature.scale) * feature.changed_values if feature else None,
                "edit_count": feature.changed_values if feature else None,
                "evaluations": feature.evaluations if feature else 20,
                "generated_candidates": None,
                "invalid_candidates": None,
                "duplicate_candidates": None,
                "runtime_seconds": feature_runtime,
                "transfer_decision_weakened": None,
                "transfer_impact_gain": None,
                "edits": [],
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
                    seed + seed_offsets["transfer"] + scenario_index,
                    audit_lead,
                    runtime,
                    search.last_evaluations,
                    search.last_generated_candidates,
                    search.last_invalid_candidates,
                    search.last_duplicate_candidates,
                    factual_trace.steps[audit_time].action,
                    float(config["minimum_impact_gain"]),
                    response_costs,  # type: ignore[arg-type]
                    float(config["switching_cost"]),
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
            (method, scenario.name) for method in METHODS for scenario in scenario_suite(config)
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
        raise ValueError(f"job artifacts come from different commits: {sorted(map(str, commits))}")
    if str(config["protocol_name"]).startswith(
        "icps_counterfactual_red_teaming_confirmatory"
    ):
        if commits == {"unavailable"}:
            raise ValueError("confirmatory artifacts do not identify a Git commit")
        if any(job.get("git_dirty") is not False for job in jobs):
            raise ValueError("confirmatory artifacts require a verified clean worktree")
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
        generated = [
            float(row["generated_candidates"])
            for row in rows
            if row.get("generated_candidates") is not None
        ]
        invalid = [
            float(row["invalid_candidates"])
            for row in rows
            if row.get("invalid_candidates") is not None
        ]
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
            "median_generated_candidates": statistics.median(generated) if generated else None,
            "median_invalid_candidates": statistics.median(invalid) if invalid else None,
            "median_runtime_seconds": statistics.median(runtimes),
            "transfer_valid_rate": sum(
                row.get("transfer_decision_weakened") is True
                and (row.get("transfer_impact_gain") or 0.0) > 0.0
                for row in found
            ) / max(1, len(found)),
        }
    summary["paired_proposed_minus_random_valid"] = _paired_validity_difference(
        records, "proposed", "random_valid", int(config["bootstrap_seed"])
    )
    summary["paired_proposed_minus_cyber_only"] = _paired_validity_difference(
        records, "proposed", "cyber_only", int(config["bootstrap_seed"]) + 1
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
    records: list[dict[str, Any]], left: str, right: str, bootstrap_seed: int
) -> dict[str, int | float | list[float]]:
    keyed = {(row["job_index"], row["scenario_index"], row["method"]): row for row in records}

    def valid(row: dict[str, Any]) -> float:
        return float(
            row.get("decision_weakened") is True
            and row.get("cyber_feasible") is True
            and row.get("physical_executable") is True
            and row.get("impact_valid") is True
        )

    # Scenarios evaluated with the same learned policy are correlated. Reduce
    # each method to one validity rate per policy seed, then resample those
    # independent policy-level paired differences.
    differences: list[float] = []
    job_indices = sorted({int(row["job_index"]) for row in records})
    scenario_indices = sorted({int(row["scenario_index"]) for row in records})
    for job_index in job_indices:
        left_rate = statistics.mean(
            valid(keyed[(job_index, scenario_index, left)])
            for scenario_index in scenario_indices
        )
        right_rate = statistics.mean(
            valid(keyed[(job_index, scenario_index, right)])
            for scenario_index in scenario_indices
        )
        differences.append(left_rate - right_rate)
    observed = statistics.mean(differences) if differences else 0.0
    # Deterministic paired bootstrap over independent policy seeds.
    import random

    rng = random.Random(bootstrap_seed)
    samples = []
    if differences:
        for _ in range(5000):
            samples.append(statistics.mean(rng.choice(differences) for _ in differences))
        samples.sort()
        low = samples[int(0.025 * (len(samples) - 1))]
        high = samples[int(0.975 * (len(samples) - 1))]
    else:
        low = high = 0.0
    return {
        "policy_seeds": len(differences),
        "mean_difference": observed,
        "bootstrap_95_ci": [low, high],
    }


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
        "median_generated_candidates",
        "median_invalid_candidates",
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
