"""Reproducible pilot experiment and artifact generation."""

from __future__ import annotations

import csv
import json
import random
import statistics
from dataclasses import asdict
from pathlib import Path

from ..core.campaign import reference_campaign
from ..core.domain import AttackStage, Campaign
from ..explainers.counterfactual import CounterfactualSearch, SearchConfig
from ..models.responder import QLearningResponder
from ..simulators.simulation import ICPSSimulator, SimulationConfig
from .metrics import maximum_band_deviation


def _training_campaign(rng: random.Random, episode: int) -> Campaign:
    campaign = reference_campaign(
        name=f"train_{episode:04d}",
        offset=rng.choice((-2, -1, 0, 1, 2)),
        impact_magnitude=rng.uniform(0.72, 1.18),
    )
    events = []
    for event in campaign.events:
        visibility = max(0.18, min(1.0, event.visibility * rng.uniform(0.70, 1.15)))
        events.append(event.edited(visibility=visibility))
    return Campaign(campaign.name, tuple(events))


def train_responder(seed: int, episodes: int, horizon: int) -> QLearningResponder:
    rng = random.Random(seed)
    learner = QLearningResponder(seed=seed)
    simulator = ICPSSimulator(SimulationConfig(horizon=horizon))
    for episode in range(episodes):
        epsilon = max(0.03, 0.55 * (1.0 - episode / max(1, episodes)))
        simulator.train_episode(
            _training_campaign(rng, episode),
            learner,
            seed=seed + 10_000 + episode,
            epsilon=epsilon,
        )
    return learner


def run_pilot(
    config: dict[str, object],
    root: Path,
    *,
    write_artifacts: bool = True,
) -> dict[str, object]:
    seed = int(config["seed"])
    episodes = int(config["training_episodes"])
    horizon = int(config["horizon"])
    learner = train_responder(seed, episodes, horizon)
    frozen = learner.freeze()
    simulator = ICPSSimulator(SimulationConfig(horizon=horizon))
    search = CounterfactualSearch(
        simulator,
        config=SearchConfig(
            depth=int(config["search_depth"]),
            beam_width=int(config["beam_width"]),
            audit_lead=int(config["audit_lead"]),
            minimum_impact_gain=float(config["minimum_impact_gain"]),
            seed=seed + 91,
        ),
    )
    factual = reference_campaign(name="held_out_reference", impact_magnitude=1.12)
    result = search.search(factual, frozen)

    if write_artifacts:
        root.joinpath("results").mkdir(parents=True, exist_ok=True)
        learner.save(root / "results" / "frozen_q_table.json")
    if result is None:
        payload: dict[str, object] = {
            "status": "no_counterfactual_found",
            "seed": seed,
            "training_episodes": episodes,
        }
    else:
        impact_time = next(
            event.time
            for event in result.counterfactual_campaign.events
            if event.stage is AttackStage.ACTUATOR_OVERRIDE
        )
        transfer_simulator = ICPSSimulator(SimulationConfig(horizon=horizon, high_fidelity=True))
        factual_transfer = transfer_simulator.run(result.factual_campaign, frozen, seed=seed + 191)
        counterfactual_transfer = transfer_simulator.run(result.counterfactual_campaign, frozen, seed=seed + 191)
        transfer_factual_action = factual_transfer.steps[impact_time - int(config["audit_lead"])].action
        transfer_counterfactual_action = counterfactual_transfer.steps[impact_time - int(config["audit_lead"])].action
        transfer_factual_impact = maximum_band_deviation(factual_transfer, impact_time)
        transfer_counterfactual_impact = maximum_band_deviation(counterfactual_transfer, impact_time)
        payload = {
            "status": "counterfactual_found",
            "seed": seed,
            "training_episodes": episodes,
            "factual_action": result.factual_action.name,
            "counterfactual_action": result.counterfactual_action.name,
            "factual_impact": result.factual_impact,
            "counterfactual_impact": result.counterfactual_impact,
            "impact_gain": result.impact_gain,
            "edit_cost": result.edit_cost,
            "evaluations": result.evaluations,
            "transfer_factual_action": transfer_factual_action.name,
            "transfer_counterfactual_action": transfer_counterfactual_action.name,
            "transfer_decision_weakened": transfer_counterfactual_action < transfer_factual_action,
            "transfer_impact_gain": transfer_counterfactual_impact - transfer_factual_impact,
            "edits": [asdict(edit) for edit in result.edits],
        }
    if write_artifacts:
        (root / "results" / "pilot.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        _write_csv(root / "results" / "pilot.csv", payload)
        _write_latex(root / "paper" / "generated" / "pilot_table.tex", payload)
    return payload


def run_study(config: dict[str, object], root: Path) -> dict[str, object]:
    """Repeat the complete pipeline over disjoint responder seeds."""

    base_seed = int(config["seed"])
    seed_count = int(config["evaluation_seeds"])
    rows: list[dict[str, object]] = []
    for index in range(seed_count):
        run_seed = base_seed + 7_919 * index
        local = dict(config)
        local["seed"] = run_seed
        # Temporary artifacts are overwritten by each run; the aggregate is
        # written after all independent policies have been evaluated.
        row = run_pilot(local, root, write_artifacts=False)
        row["run_index"] = index
        rows.append(row)

    successes = [row for row in rows if row["status"] == "counterfactual_found"]
    summary: dict[str, object] = {
        "runs": seed_count,
        "successes": len(successes),
        "success_rate": len(successes) / seed_count,
        "transfer_successes": sum(bool(row.get("transfer_decision_weakened", False)) for row in successes),
    }
    for key in ("impact_gain", "edit_cost", "evaluations", "transfer_impact_gain"):
        values = [float(row[key]) for row in successes]
        if values:
            summary[f"{key}_median"] = statistics.median(values)
            if len(values) >= 4:
                quartiles = statistics.quantiles(values, n=4, method="inclusive")
                summary[f"{key}_q1"] = quartiles[0]
                summary[f"{key}_q3"] = quartiles[2]

    artifact = {"status": "engineering_multiseed", "summary": summary, "runs": rows}
    results_dir = root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "study.json").write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    _write_study_csv(results_dir / "study.csv", rows)
    _write_study_latex(root / "paper" / "generated" / "study_table.tex", summary)
    return artifact


def _write_csv(path: Path, payload: dict[str, object]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("metric", "value"))
        for key, value in payload.items():
            if key != "edits":
                writer.writerow((key, value))


def _write_study_csv(path: Path, rows: list[dict[str, object]]) -> None:
    keys = (
        "run_index",
        "seed",
        "status",
        "factual_action",
        "counterfactual_action",
        "impact_gain",
        "edit_cost",
        "evaluations",
        "transfer_decision_weakened",
        "transfer_impact_gain",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _latex_escape(value: object) -> str:
    return str(value).replace("_", "\\_")


def _write_latex(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if payload["status"] != "counterfactual_found":
        content = "% Pilot did not find a counterfactual; confirmatory table pending.\n"
    else:
        content = "\n".join(
            (
                "\\begin{table}[t]",
                "\\caption{Single-seed engineering pilot. These values are not confirmatory results.}",
                "\\label{tab:pilot}",
                "\\centering",
                "\\begin{tabular}{lc}",
                "\\hline",
                "Quantity & Pilot value \\\\",
                "\\hline",
                f"Factual response & {_latex_escape(payload['factual_action'])} \\\\",
                f"Counterfactual response & {_latex_escape(payload['counterfactual_action'])} \\\\",
                f"Impact gain & {float(payload['impact_gain']):.4f} \\\\",
                f"Edit cost & {float(payload['edit_cost']):.3f} \\\\",
                f"Simulator evaluations & {int(payload['evaluations'])} \\\\",
                f"Transfer decision weakened & {_latex_escape(payload['transfer_decision_weakened'])} \\\\",
                f"Transfer impact gain & {float(payload['transfer_impact_gain']):.4f} \\\\",
                "\\hline",
                "\\end{tabular}",
                "\\end{table}",
                "",
            )
        )
    path.write_text(content, encoding="utf-8")


def _write_study_latex(path: Path, summary: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    success_rate = 100.0 * float(summary["success_rate"])
    transfer_rate = (
        100.0 * int(summary["transfer_successes"]) / max(1, int(summary["successes"]))
    )
    content = "\n".join(
        (
            "\\begin{table}[t]",
            "\\caption{Multi-seed engineering study. Confirmatory baseline comparisons remain pending.}",
            "\\label{tab:engineering-study}",
            "\\centering",
            "\\begin{tabular}{lc}",
            "\\toprule",
            "Quantity & Value \\\\",
            "\\midrule",
            f"Independent runs & {int(summary['runs'])} \\\\",
            f"Counterfactual success & {success_rate:.1f}\\% \\\\",
            f"Median impact gain & {float(summary.get('impact_gain_median', 0.0)):.4f} \\\\",
            f"Median edit cost & {float(summary.get('edit_cost_median', 0.0)):.3f} \\\\",
            f"Median evaluations & {float(summary.get('evaluations_median', 0.0)):.0f} \\\\",
            f"Transfer decision validity & {transfer_rate:.1f}\\% \\\\",
            f"Median transfer impact gain & {float(summary.get('transfer_impact_gain_median', 0.0)):.4f} \\\\",
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
            "",
        )
    )
    path.write_text(content, encoding="utf-8")
