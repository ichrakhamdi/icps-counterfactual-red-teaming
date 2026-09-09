from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from icps_xai.core.campaign import reference_campaign
from icps_xai.core.domain import Observation, PlantState, ResponseAction
from icps_xai.evaluation.feasibility import PhysicalFeasibilityChecker
from icps_xai.models.plant import ThreeStageWaterPlant
from icps_xai.models.responder import FrozenResponder
from icps_xai.simulators.simulation import ICPSSimulator


class MonitorPolicy:
    def reset(self) -> None:
        return None

    def act(self, observation: Observation) -> ResponseAction:
        return ResponseAction.MONITOR


class SimulationTests(unittest.TestCase):
    def test_measurement_replay_changes_only_its_target_sensor(self) -> None:
        plant = ThreeStageWaterPlant(seed=17)
        plant.state = PlantState((0.80, 0.70, 0.60), (0.0, 0.0, 0.0, 0.0))
        plant._history = [(0.20, 0.30, 0.40)] * 13
        delivered = plant.delivered_levels(1.0, replay_sensor=0)
        self.assertAlmostEqual(delivered[0], 0.20, delta=0.01)
        self.assertAlmostEqual(delivered[1], 0.70, delta=0.01)
        self.assertAlmostEqual(delivered[2], 0.60, delta=0.01)

    def test_actuator_targets_have_distinct_physical_effects(self) -> None:
        inlet_plant = ThreeStageWaterPlant(seed=3)
        pump_plant = ThreeStageWaterPlant(seed=3)
        delivered = inlet_plant.state.levels
        inlet = inlet_plant.step(delivered, 1.0, "inlet_valve", ResponseAction.MONITOR)
        pump = pump_plant.step(delivered, 1.0, "transfer_pump", ResponseAction.MONITOR)
        self.assertGreater(inlet.flows[0], pump.flows[0])
        self.assertGreater(inlet.flows[1], pump.flows[1])
        self.assertNotEqual(inlet.levels, pump.levels)

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
