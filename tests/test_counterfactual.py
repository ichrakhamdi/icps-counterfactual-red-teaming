from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from icps_xai.campaign import CampaignValidator
from icps_xai.experiment import run_pilot


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


if __name__ == "__main__":
    unittest.main()

