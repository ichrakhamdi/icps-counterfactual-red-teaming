from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from icps_xai.campaign import CampaignValidator, campaign_neighbors, reference_campaign
from icps_xai.domain import AttackStage
from icps_xai.topology import CyberTopology, DEFAULT_EDGES


class CampaignTests(unittest.TestCase):
    def test_reference_campaign_is_valid(self) -> None:
        result = CampaignValidator().validate(reference_campaign(), horizon=100)
        self.assertTrue(result.valid, result.errors)

    def test_stage_order_is_enforced(self) -> None:
        campaign = reference_campaign()
        broken = campaign.with_event(2, campaign.events[2].edited(time=4), "broken")
        result = CampaignValidator().validate(broken, horizon=100)
        self.assertFalse(result.valid)
        self.assertTrue(any("must precede" in error for error in result.errors))

    def test_search_edits_hold_physical_impact_event_fixed(self) -> None:
        campaign = reference_campaign()
        impact = next(event for event in campaign.events if event.stage is AttackStage.ACTUATOR_OVERRIDE)
        for neighbor, _ in campaign_neighbors(campaign):
            changed = next(event for event in neighbor.events if event.stage is AttackStage.ACTUATOR_OVERRIDE)
            self.assertEqual(impact, changed)

    def test_network_reachability_is_enforced(self) -> None:
        disconnected = CyberTopology(
            frozenset(edge for edge in DEFAULT_EDGES if edge != ("engineering_workstation", "plc2"))
        )
        result = CampaignValidator(disconnected).validate(reference_campaign(), horizon=100)
        self.assertFalse(result.valid)
        self.assertTrue(any("PLC_DISCOVERY cannot reach plc2" in error for error in result.errors))

    def test_required_stage_cannot_be_replaced_by_reachability(self) -> None:
        campaign = reference_campaign()
        incomplete = type(campaign)(campaign.name, tuple(event for event in campaign.events if event.stage is not AttackStage.PLC_DISCOVERY))
        result = CampaignValidator().validate(incomplete, horizon=100)
        self.assertFalse(result.valid)
        self.assertTrue(any("lacks PLC_DISCOVERY" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
