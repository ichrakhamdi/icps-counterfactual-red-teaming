"""Independent numerical and transfer checks for reported campaigns."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .campaign import CampaignValidator
from .domain import Campaign
from .responder import FrozenResponder
from .simulation import ICPSSimulator, SimulationConfig


@dataclass(frozen=True)
class FeasibilityReport:
    valid: bool
    cyber_valid: bool
    numerical_valid: bool
    checked_runs: int
    errors: tuple[str, ...]


class PhysicalFeasibilityChecker:
    """Replays a campaign under both execution models and independent seeds."""

    def __init__(self, horizon: int, seeds: tuple[int, ...] = (101, 211, 307)) -> None:
        self.horizon = horizon
        self.seeds = seeds
        self.validator = CampaignValidator()

    def check(self, campaign: Campaign, policy: FrozenResponder) -> FeasibilityReport:
        cyber = self.validator.validate(campaign, self.horizon)
        errors = list(cyber.errors)
        runs = 0
        numerical = True
        if cyber.valid:
            for high_fidelity in (False, True):
                simulator = ICPSSimulator(
                    SimulationConfig(horizon=self.horizon, high_fidelity=high_fidelity)
                )
                for seed in self.seeds:
                    trace = simulator.run(campaign, policy.clone(), seed=seed)
                    runs += 1
                    for step in trace.steps:
                        values = (*step.state.levels, *step.state.flows)
                        if not all(math.isfinite(value) for value in values):
                            numerical = False
                            errors.append(f"non-finite state in run {runs} at cycle {step.time}")
                        if any(level < 0.0 or level > 1.35 for level in step.state.levels):
                            numerical = False
                            errors.append(f"state outside model domain in run {runs} at cycle {step.time}")
        else:
            numerical = False
        return FeasibilityReport(cyber.valid and numerical, cyber.valid, numerical, runs, tuple(errors))
