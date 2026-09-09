"""Trace metrics used by search and evaluation."""

from __future__ import annotations

from ..core.domain import ResponseAction, Trace


TARGETS = (0.66, 0.62, 0.58)
HARD_LIMITS = (0.20, 1.12)


def maximum_band_deviation(trace: Trace, start: int = 0) -> float:
    return max(
        max(abs(level - target) for level, target in zip(step.state.levels, TARGETS))
        for step in trace.steps[start:]
    )


def out_of_limit_cycles(trace: Trace) -> int:
    low, high = HARD_LIMITS
    return sum(any(level < low or level > high for level in step.state.levels) for step in trace.steps)


def peak_action(trace: Trace, start: int, end: int) -> ResponseAction:
    return max((step.action for step in trace.steps[start:end]), default=ResponseAction.MONITOR)


def availability(trace: Trace) -> float:
    return sum(step.observation.availability for step in trace.steps) / len(trace.steps)
