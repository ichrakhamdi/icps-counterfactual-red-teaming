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
        self.config = {
            "protocol_name": "unit_test",
            "training_episodes": 8,
            "evaluation_policy_seeds": [101],
            "horizon": 100,
            "audit_lead": 1,
            "search_depth": 1,
            "beam_width": 3,
            "search_evaluation_budget": 5,
            "minimum_impact_gain": 0.001,
        }

    def test_job_has_complete_method_scenario_grid_and_aggregates(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            output = Path(directory)
            job = run_job(self.config, ROOT, 0, output)
            pairs = {(row["method"], row["scenario"]) for row in job["records"]}
            expected = {(method, scenario.name) for method in METHODS for scenario in scenario_suite()}
            self.assertEqual(pairs, expected)
            aggregate = aggregate_jobs(self.config, output, output / "aggregate.json")
            self.assertEqual(aggregate["jobs"], 1)
            self.assertTrue(set(METHODS).issubset(aggregate["summary"]))
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


if __name__ == "__main__":
    unittest.main()
