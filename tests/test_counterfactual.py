from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from icps_xai.core.campaign import CampaignValidator
from icps_xai.evaluation.experiment import run_pilot


class CounterfactualIntegrationTests(unittest.TestCase):
    def test_pilot_returns_replayable_valid_counterfactual(self) -> None:
        config = json.loads((ROOT / "configs" / "default.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as directory:
            temporary_root = Path(directory)
            temporary_root.joinpath("paper", "generated").mkdir(parents=True)
            result = run_pilot(config, temporary_root)
            self.assertEqual(result["status"], "counterfactual_found")
            self.assertNotEqual(result["factual_action"], result["counterfactual_action"])
            self.assertGreater(result["impact_gain"], 0.0)
            self.assertTrue((temporary_root / "results" / "pilot.json").exists())

    def test_pilot_creates_a_new_output_root(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            root = Path(directory) / "new-artifact-root"
            config = json.loads((ROOT / "configs" / "default.json").read_text(encoding="utf-8"))
            config["training_episodes"] = 8
            run_pilot(config, root)
            self.assertTrue((root / "results" / "pilot.json").is_file())
            self.assertTrue((root / "paper" / "generated" / "pilot_table.tex").is_file())


if __name__ == "__main__":
    unittest.main()
