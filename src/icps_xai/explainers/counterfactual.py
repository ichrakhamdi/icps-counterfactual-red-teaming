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
        self.last_generated_candidates = 0
        self.last_invalid_candidates = 0
        self.last_duplicate_candidates = 0

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

    def _rank(
        self, node: _Node, factual_action: int, factual_impact: float
    ) -> tuple[float, float, float]:
        action_drop = factual_action - node.action_value
        impact_gain = node.impact - factual_impact
        if self.config.require_impact_gain:
            return action_drop, impact_gain, -node.cost
        # The cyber-only ablation must not use a physical outcome to guide its
        # frontier. Its proposal order depends only on the policy target and
        # campaign edit cost.
        return action_drop, -node.cost, 0.0

    def _solution_key(
        self, node: _Node, factual_action: int, factual_impact: float
    ) -> tuple[float, float, float]:
        impact_priority = -(node.impact - factual_impact) if self.config.require_impact_gain else 0.0
        return node.cost, -(factual_action - node.action_value), impact_priority

    def search(self, factual: Campaign, policy: FrozenResponder) -> CounterfactualResult | None:
        validation = self.validator.validate(factual, self.simulator.config.horizon)
        if not validation.valid:
            raise ValueError("factual campaign is invalid")
        factual_action, factual_impact = self._evaluate(factual, policy)
        frontier = [_Node(factual, (), factual_action, factual_impact)]
        factual_signature = factual.signature()
        best_path_cost = {factual_signature: 0.0}
        evaluation_cache = {factual_signature: (factual_action, factual_impact)}
        evaluations = 1
        self.last_evaluations = evaluations
        self.last_generated_candidates = 0
        self.last_invalid_candidates = 0
        self.last_duplicate_candidates = 0
        valid_solutions: list[_Node] = []

        for _ in range(self.config.depth):
            expanded: list[_Node] = []
            for node in frontier:
                for candidate, edit in campaign_neighbors(node.campaign):
                    self.last_generated_candidates += 1
                    signature = candidate.signature()
                    child_edits = node.edits + (edit,)
                    child_cost = sum(item.cost for item in child_edits)
                    if child_cost >= best_path_cost.get(signature, float("inf")):
                        self.last_duplicate_candidates += 1
                        continue
                    if not self.validator.validate(candidate, self.simulator.config.horizon).valid:
                        self.last_invalid_candidates += 1
                        continue
                    best_path_cost[signature] = child_cost
                    cached = evaluation_cache.get(signature)
                    if cached is None:
                        if evaluations >= self.config.max_evaluations:
                            break
                        cached = self._evaluate(candidate, policy)
                        evaluation_cache[signature] = cached
                        evaluations += 1
                        self.last_evaluations = evaluations
                    action_value, impact = cached
                    child = _Node(candidate, child_edits, action_value, impact)
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
            key=lambda node: self._solution_key(node, factual_action, factual_impact),
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
        self.last_generated_candidates = 0
        self.last_invalid_candidates = 0
        self.last_duplicate_candidates = 0
        solutions: list[_Node] = []
        while evaluations < self.config.max_evaluations:
            campaign = factual
            edits: tuple[CampaignEdit, ...] = ()
            for _ in range(rng.randint(1, self.config.depth)):
                choices = []
                for pair in campaign_neighbors(campaign):
                    self.last_generated_candidates += 1
                    if self.validator.validate(pair[0], self.simulator.config.horizon).valid:
                        choices.append(pair)
                    else:
                        self.last_invalid_candidates += 1
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
            key=lambda node: self._solution_key(node, factual_action, factual_impact),
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
