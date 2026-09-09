from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from icps_xai.evaluation.protocol import (
    METHODS,
    aggregate_jobs,
    run_job,
    scenario_suite,
    write_confirmatory_latex,
)


class ProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads((ROOT / "configs" / "smoke.json").read_text(encoding="utf-8"))
        self.config.update(
            protocol_name="unit_test",
            training_episodes=8,
            evaluation_policy_seeds=[101],
            search_depth=1,
            beam_width=3,
            search_evaluation_budget=5,
        )

    def test_job_has_complete_method_scenario_grid_and_aggregates(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            output = Path(directory)
            job = run_job(self.config, ROOT, 0, output)
            pairs = {(row["method"], row["scenario"]) for row in job["records"]}
            common_fields = {
                "method",
                "status",
                "factual_action",
                "counterfactual_action",
                "impact_gain",
                "edit_cost",
                "evaluations",
                "runtime_seconds",
                "transfer_decision_weakened",
                "transfer_impact_gain",
                "edits",
            }
            self.assertTrue(all(common_fields <= set(row) for row in job["records"]))
            expected = {
                (method, scenario.name)
                for method in METHODS
                for scenario in scenario_suite(self.config)
            }
            self.assertEqual(pairs, expected)
            aggregate = aggregate_jobs(self.config, output, output / "aggregate.json")
            self.assertEqual(aggregate["jobs"], 1)
            self.assertTrue(set(METHODS).issubset(aggregate["summary"]))
            self.assertEqual(
                aggregate["summary"]["paired_proposed_minus_cyber_only"]["policy_seeds"],
                1,
            )
            self.assertIn("median_invalid_candidates", aggregate["summary"]["proposed"])
            self.assertTrue((output / "aggregate.csv").exists())
            table = output / "confirmatory_table.tex"
            write_confirmatory_latex(table, aggregate["summary"])
            self.assertIn("Cyber-physical CF", table.read_text(encoding="utf-8"))

    def test_aggregate_rejects_wrong_config(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            output = Path(directory)
            run_job(self.config, ROOT, 0, output)
            changed = dict(self.config, training_episodes=9)
            with self.assertRaises(ValueError):
                aggregate_jobs(changed, output, output / "aggregate.json")

    def test_confirmatory_aggregate_requires_verified_clean_provenance(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            output = Path(directory)
            config = dict(
                self.config,
                protocol_name="icps_counterfactual_red_teaming_confirmatory_test",
            )
            run_job(config, ROOT, 0, output)
            path = output / "job_0000.json"
            artifact = json.loads(path.read_text(encoding="utf-8"))
            artifact["git_commit"] = "test-commit"
            artifact["git_dirty"] = None
            path.write_text(json.dumps(artifact), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "verified clean worktree"):
                aggregate_jobs(config, output, output / "aggregate.json")


if __name__ == "__main__":
    unittest.main()
