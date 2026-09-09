"""Black-box search for executable campaign-level counterfactual explanations."""

from __future__ import annotations

from dataclasses import dataclass
import random

from ..core.campaign import CampaignValidator, campaign_neighbors
from ..core.domain import AttackStage, Campaign, CampaignEdit, CounterfactualResult
from ..evaluation.metrics import maximum_band_deviation
from ..models.responder import FrozenResponder
from ..simulators.simulation import ICPSSimulator


@dataclass(frozen=True)
class SearchConfig:
    depth: int = 3
    beam_width: int = 18
    audit_lead: int = 1
    minimum_impact_gain: float = 0.002
    seed: int = 19
    max_evaluations: int = 1000
    require_impact_gain: bool = True


@dataclass
class _Node:
    campaign: Campaign
    edits: tuple[CampaignEdit, ...]
    action_value: int
    impact: float

    @property
    def cost(self) -> float:
        return sum(edit.cost for edit in self.edits)


class CounterfactualSearch:
    """Search campaign space without accessing the responder's parameters."""

    def __init__(
        self,
        simulator: ICPSSimulator,
        validator: CampaignValidator | None = None,
        config: SearchConfig | None = None,
    ) -> None:
        self.simulator = simulator
        self.validator = validator or CampaignValidator()
        self.config = config or SearchConfig()
        self.last_evaluations = 0

    @staticmethod
    def _impact_time(campaign: Campaign) -> int:
        impact_events = [event for event in campaign.events if event.stage is AttackStage.ACTUATOR_OVERRIDE]
        if not impact_events:
            raise ValueError("campaign has no actuator-impact event")
        return impact_events[0].time

    def _evaluate(self, campaign: Campaign, policy: FrozenResponder) -> tuple[int, float]:
        trace = self.simulator.run(campaign, policy, seed=self.config.seed)
        impact_time = self._impact_time(campaign)
        audit_time = max(0, impact_time - self.config.audit_lead)
        action = int(trace.steps[audit_time].action)
        impact = maximum_band_deviation(trace, impact_time)
        return action, impact

    @staticmethod
    def _rank(node: _Node, factual_action: int, factual_impact: float) -> tuple[float, float, float]:
        action_drop = factual_action - node.action_value
        impact_gain = node.impact - factual_impact
        return action_drop, impact_gain, -node.cost

    def search(self, factual: Campaign, policy: FrozenResponder) -> CounterfactualResult | None:
        validation = self.validator.validate(factual, self.simulator.config.horizon)
        if not validation.valid:
            raise ValueError("factual campaign is invalid")
        factual_action, factual_impact = self._evaluate(factual, policy)
        frontier = [_Node(factual, (), factual_action, factual_impact)]
        seen = {factual.signature()}
        evaluations = 1
        self.last_evaluations = evaluations
        valid_solutions: list[_Node] = []

        for _ in range(self.config.depth):
            expanded: list[_Node] = []
            for node in frontier:
                for candidate, edit in campaign_neighbors(node.campaign):
                    signature = candidate.signature()
                    if signature in seen:
                        continue
                    seen.add(signature)
                    if not self.validator.validate(candidate, self.simulator.config.horizon).valid:
                        continue
                    action_value, impact = self._evaluate(candidate, policy)
                    evaluations += 1
                    self.last_evaluations = evaluations
                    child = _Node(candidate, node.edits + (edit,), action_value, impact)
                    expanded.append(child)
                    impact_valid = (
                        impact - factual_impact >= self.config.minimum_impact_gain
                        if self.config.require_impact_gain
                        else True
                    )
                    if action_value < factual_action and impact_valid:
                        valid_solutions.append(child)
                    if evaluations >= self.config.max_evaluations:
                        break
                if evaluations >= self.config.max_evaluations:
                    break

            if not expanded:
                break
            expanded.sort(
                key=lambda item: self._rank(item, factual_action, factual_impact),
                reverse=True,
            )
            frontier = expanded[: self.config.beam_width]
            if evaluations >= self.config.max_evaluations:
                break

        if not valid_solutions:
            return None
        selected = min(
            valid_solutions,
            key=lambda node: (
                node.cost,
                -(factual_action - node.action_value),
                -(node.impact - factual_impact),
            ),
        )
        from ..core.domain import ResponseAction

        return CounterfactualResult(
            factual,
            selected.campaign,
            selected.edits,
            ResponseAction(factual_action),
            ResponseAction(selected.action_value),
            factual_impact,
            selected.impact,
            selected.cost,
            evaluations,
        )


class RandomValidSearch(CounterfactualSearch):
    """Matched-budget random walk over the same valid edit grammar."""

    def search(self, factual: Campaign, policy: FrozenResponder) -> CounterfactualResult | None:
        validation = self.validator.validate(factual, self.simulator.config.horizon)
        if not validation.valid:
            raise ValueError("factual campaign is invalid")
        factual_action, factual_impact = self._evaluate(factual, policy)
        rng = random.Random(self.config.seed)
        evaluations = 1
        self.last_evaluations = evaluations
        solutions: list[_Node] = []
        while evaluations < self.config.max_evaluations:
            campaign = factual
            edits: tuple[CampaignEdit, ...] = ()
            for _ in range(rng.randint(1, self.config.depth)):
                choices = [
                    pair
                    for pair in campaign_neighbors(campaign)
                    if self.validator.validate(pair[0], self.simulator.config.horizon).valid
                ]
                if not choices:
                    break
                campaign, edit = rng.choice(choices)
                edits += (edit,)
            action, impact = self._evaluate(campaign, policy)
            evaluations += 1
            self.last_evaluations = evaluations
            impact_valid = (
                impact - factual_impact >= self.config.minimum_impact_gain
                if self.config.require_impact_gain
                else True
            )
            if action < factual_action and impact_valid:
                solutions.append(_Node(campaign, edits, action, impact))
        if not solutions:
            return None
        selected = min(
            solutions,
            key=lambda node: (node.cost, -(factual_action - node.action_value), -(node.impact - factual_impact)),
        )
        from ..core.domain import ResponseAction

        return CounterfactualResult(
            factual,
            selected.campaign,
            selected.edits,
            ResponseAction(factual_action),
            ResponseAction(selected.action_value),
            factual_impact,
            selected.impact,
            selected.cost,
            evaluations,
        )
