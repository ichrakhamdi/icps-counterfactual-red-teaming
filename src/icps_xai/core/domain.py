"""Shared immutable domain objects."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import IntEnum
from typing import Iterable


class AttackStage(IntEnum):
    CREDENTIAL_ACCESS = 0
    ENGINEERING_ACCESS = 1
    PLC_DISCOVERY = 2
    HISTORIAN_IMPAIRMENT = 3
    MEASUREMENT_REPLAY = 4
    ACTUATOR_OVERRIDE = 5


class ResponseAction(IntEnum):
    MONITOR = 0
    INSPECT = 1
    RESTRICT = 2
    BACKUP = 3


@dataclass(frozen=True)
class CampaignEvent:
    stage: AttackStage
    time: int
    asset: str
    magnitude: float = 1.0
    visibility: float = 1.0
    duration: int = 1

    def edited(self, **changes: object) -> "CampaignEvent":
        return replace(self, **changes)


@dataclass(frozen=True)
class Campaign:
    name: str
    events: tuple[CampaignEvent, ...]

    def sorted(self) -> "Campaign":
        return Campaign(self.name, tuple(sorted(self.events, key=lambda e: (e.time, int(e.stage)))))

    def with_event(self, index: int, event: CampaignEvent, suffix: str) -> "Campaign":
        values = list(self.events)
        values[index] = event
        return Campaign(f"{self.name}|{suffix}", tuple(values)).sorted()

    def signature(self) -> tuple[tuple[int, int, str, int, int, int], ...]:
        return tuple(
            (
                int(event.stage),
                event.time,
                event.asset,
                round(event.magnitude * 1000),
                round(event.visibility * 1000),
                event.duration,
            )
            for event in self.events
        )


@dataclass(frozen=True)
class Observation:
    delivered_levels: tuple[float, float, float]
    flows: tuple[float, float, float, float]
    authentication_alert: float
    discovery_alert: float
    historian_gap: float
    controller_write_alert: float
    model_residual: float
    availability: float
    previous_action: ResponseAction

    def evidence(self) -> float:
        return max(
            self.authentication_alert,
            self.discovery_alert,
            self.historian_gap,
            self.controller_write_alert,
            min(1.0, self.model_residual * 7.5),
        )


@dataclass(frozen=True)
class PlantState:
    levels: tuple[float, float, float]
    flows: tuple[float, float, float, float]


@dataclass(frozen=True)
class TraceStep:
    time: int
    state: PlantState
    observation: Observation
    action: ResponseAction
    active_stage: AttackStage | None
    attack_intensity: float
    reward: float


@dataclass(frozen=True)
class Trace:
    campaign: Campaign
    steps: tuple[TraceStep, ...]

    def actions(self, start: int = 0, end: int | None = None) -> tuple[ResponseAction, ...]:
        stop = len(self.steps) if end is None else end
        return tuple(step.action for step in self.steps[start:stop])

    def levels(self) -> Iterable[tuple[float, float, float]]:
        return (step.state.levels for step in self.steps)


@dataclass(frozen=True)
class CampaignEdit:
    event_index: int
    field: str
    before: float | int
    after: float | int
    cost: float


@dataclass(frozen=True)
class CounterfactualResult:
    factual_campaign: Campaign
    counterfactual_campaign: Campaign
    edits: tuple[CampaignEdit, ...]
    factual_action: ResponseAction
    counterfactual_action: ResponseAction
    factual_impact: float
    counterfactual_impact: float
    edit_cost: float
    evaluations: int

    @property
    def decision_weakened(self) -> bool:
        return self.counterfactual_action < self.factual_action

    @property
    def impact_gain(self) -> float:
        return self.counterfactual_impact - self.factual_impact
