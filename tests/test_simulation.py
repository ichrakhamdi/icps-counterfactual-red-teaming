from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from icps_xai.campaign import reference_campaign
from icps_xai.domain import Observation, ResponseAction
from icps_xai.simulation import ICPSSimulator
from icps_xai.feasibility import PhysicalFeasibilityChecker
from icps_xai.responder import FrozenResponder


class MonitorPolicy:
    def reset(self) -> None:
        return None

    def act(self, observation: Observation) -> ResponseAction:
        return ResponseAction.MONITOR


class SimulationTests(unittest.TestCase):
    def test_seeded_execution_is_reproducible(self) -> None:
        simulator = ICPSSimulator()
        campaign = reference_campaign()
        first = simulator.run(campaign, MonitorPolicy(), seed=101)
        second = simulator.run(campaign, MonitorPolicy(), seed=101)
        self.assertEqual(first.steps, second.steps)

    def test_campaign_produces_physical_motion(self) -> None:
        trace = ICPSSimulator().run(reference_campaign(), MonitorPolicy(), seed=4)
        initial = trace.steps[0].state.levels
        final = trace.steps[-1].state.levels
        self.assertNotEqual(initial, final)
        self.assertTrue(all(0.0 <= value <= 1.35 for value in final))

    def test_physical_feasibility_replays_both_execution_models(self) -> None:
        policy = FrozenResponder({})
        report = PhysicalFeasibilityChecker(100, seeds=(7, 11)).check(reference_campaign(), policy)
        self.assertTrue(report.valid, report.errors)
        self.assertEqual(report.checked_runs, 4)

    def test_frozen_policy_digest_is_stable_across_execution(self) -> None:
        policy = FrozenResponder({(0, 0, 0, 0): (1.0, 0.0, 0.0, 0.0)})
        before = policy.digest()
        ICPSSimulator().run(reference_campaign(), policy, seed=9)
        self.assertEqual(before, policy.digest())


if __name__ == "__main__":
    unittest.main()
