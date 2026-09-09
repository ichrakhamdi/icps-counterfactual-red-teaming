from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from icps_xai.core.campaign import CampaignValidator, reference_campaign
from icps_xai.core.domain import CampaignEdit
from icps_xai.evaluation.experiment import run_pilot
from icps_xai.explainers.counterfactual import CounterfactualSearch, SearchConfig, _Node
from icps_xai.models.responder import FrozenResponder
from icps_xai.simulators.simulation import ICPSSimulator


class CounterfactualIntegrationTests(unittest.TestCase):
    def test_cyber_only_ranking_does_not_use_physical_impact(self) -> None:
        campaign = reference_campaign()
        edit = CampaignEdit(0, "visibility", 0.9, 0.8, 0.1)
        low_impact = _Node(campaign, (edit,), 0, 0.1)
        high_impact = _Node(campaign, (edit,), 0, 0.9)
        cyber_only = CounterfactualSearch(
            ICPSSimulator(), config=SearchConfig(require_impact_gain=False)
        )
        proposed = CounterfactualSearch(
            ICPSSimulator(), config=SearchConfig(require_impact_gain=True)
        )
        self.assertEqual(cyber_only._rank(low_impact, 1, 0.0), cyber_only._rank(high_impact, 1, 0.0))
        self.assertEqual(
            cyber_only._solution_key(low_impact, 1, 0.0),
            cyber_only._solution_key(high_impact, 1, 0.0),
        )
        self.assertLess(proposed._rank(low_impact, 1, 0.0), proposed._rank(high_impact, 1, 0.0))

    def test_search_reports_rejected_campaign_proposals(self) -> None:
        search = CounterfactualSearch(
            ICPSSimulator(),
            config=SearchConfig(depth=1, beam_width=10, max_evaluations=30),
        )
        search.search(reference_campaign(), FrozenResponder({}))
        self.assertGreater(search.last_generated_candidates, 0)
        self.assertGreater(search.last_invalid_candidates, 0)
        self.assertLessEqual(search.last_evaluations, 30)

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
