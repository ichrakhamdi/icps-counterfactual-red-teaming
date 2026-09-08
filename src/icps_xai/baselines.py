"""Baselines for the confirmatory counterfactual comparison."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .domain import Observation, ResponseAction, Trace
from .responder import FrozenResponder


@dataclass(frozen=True)
class FeatureCounterfactualResult:
    factual_action: ResponseAction
    counterfactual_action: ResponseAction
    scale: float
    window: int
    changed_values: int
    evaluations: int

    @property
    def decision_weakened(self) -> bool:
        return self.counterfactual_action < self.factual_action


def _scale_evidence(observation: Observation, scale: float) -> Observation:
    targets = (0.66, 0.62, 0.58)
    return replace(
        observation,
        delivered_levels=tuple(
            target + scale * (level - target)
            for level, target in zip(observation.delivered_levels, targets)
        ),
        authentication_alert=observation.authentication_alert * scale,
        discovery_alert=observation.discovery_alert * scale,
        historian_gap=observation.historian_gap * scale,
        controller_write_alert=observation.controller_write_alert * scale,
        model_residual=observation.model_residual * scale,
    )


def feature_counterfactual(
    trace: Trace,
    policy: FrozenResponder,
    audit_time: int,
) -> FeatureCounterfactualResult | None:
    """Find a decision flip in observation space, without claiming executability."""

    factual = trace.steps[audit_time].action
    evaluations = 0
    solutions: list[FeatureCounterfactualResult] = []
    for window in (1, 3, 6, 12, audit_time + 1):
        for scale in (0.75, 0.50, 0.25, 0.0):
            clone = policy.clone()
            action = ResponseAction.MONITOR
            start = max(0, audit_time - window + 1)
            for index in range(audit_time + 1):
                observation = trace.steps[index].observation
                observation = replace(observation, previous_action=action)
                if index >= start:
                    observation = _scale_evidence(observation, scale)
                action = clone.act(observation)
            evaluations += 1
            if action < factual:
                solutions.append(
                    FeatureCounterfactualResult(
                        factual,
                        action,
                        scale,
                        audit_time - start + 1,
                        8 * (audit_time - start + 1),
                        evaluations,
                    )
                )
    if not solutions:
        return None
    selected = min(solutions, key=lambda result: (result.changed_values, 1.0 - result.scale))
    return replace(selected, evaluations=evaluations)
