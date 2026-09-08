"""Small three-stage process model used only by this repository."""

from __future__ import annotations

import math
import random

from .domain import PlantState, ResponseAction


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class ThreeStageWaterPlant:
    """Coupled three-tank process with a central nominal controller."""

    target = (0.66, 0.62, 0.58)
    operating_band = (0.42, 0.86)
    hard_limits = (0.20, 1.12)

    def __init__(self, seed: int = 0, high_fidelity: bool = False) -> None:
        self.rng = random.Random(seed)
        self.high_fidelity = high_fidelity
        self.dt = 0.16 if high_fidelity else 0.25
        self.substeps = 2 if high_fidelity else 1
        self.areas = (1.7, 1.5, 1.35) if high_fidelity else (1.65, 1.45, 1.30)
        self.state = PlantState((0.66, 0.62, 0.58), (0.0, 0.0, 0.0, 0.0))
        self._history: list[tuple[float, float, float]] = [self.state.levels]

    def reset(self) -> PlantState:
        self.state = PlantState((0.66, 0.62, 0.58), (0.0, 0.0, 0.0, 0.0))
        self._history = [self.state.levels]
        return self.state

    def delivered_levels(self, replay_strength: float) -> tuple[float, float, float]:
        true = self.state.levels
        if replay_strength > 0 and len(self._history) > 12:
            replayed = self._history[-12]
            values = tuple(
                (1.0 - replay_strength) * actual + replay_strength * old
                for actual, old in zip(true, replayed)
            )
        else:
            values = true
        noise_scale = 0.0025 if self.high_fidelity else 0.0015
        noisy = tuple(value + self.rng.gauss(0.0, noise_scale) for value in values)
        if self.high_fidelity:
            return tuple(round(value, 3) for value in noisy)  # type: ignore[return-value]
        return noisy  # type: ignore[return-value]

    def step(
        self,
        delivered: tuple[float, float, float],
        attack_intensity: float,
        response: ResponseAction,
    ) -> PlantState:
        levels = list(self.state.levels)
        mitigation = {
            ResponseAction.MONITOR: 0.0,
            ResponseAction.INSPECT: 0.12,
            ResponseAction.RESTRICT: 0.60,
            ResponseAction.BACKUP: 1.0,
        }[response]
        effective_attack = attack_intensity * (1.0 - mitigation)

        for _ in range(self.substeps):
            controller_levels = levels if response is ResponseAction.BACKUP else list(delivered)
            inlet = _clip(0.16 + 0.90 * (self.target[0] - controller_levels[0]), 0.01, 0.36)
            inlet += 0.24 * effective_attack
            flow12 = _clip(0.105 + 0.45 * (levels[0] - levels[1]), 0.01, 0.28)
            flow23 = _clip(0.095 + 0.42 * (levels[1] - levels[2]), 0.01, 0.26)
            outlet = _clip(0.085 + 0.35 * (levels[2] - self.target[2]), 0.02, 0.22)
            outlet *= 1.0 - 0.45 * effective_attack

            step_dt = self.dt / self.substeps
            derivatives = (
                (inlet - flow12) / self.areas[0],
                (flow12 - flow23) / self.areas[1],
                (flow23 - outlet) / self.areas[2],
            )
            levels = [
                _clip(level + step_dt * derivative, 0.0, 1.35)
                for level, derivative in zip(levels, derivatives)
            ]

        if not all(math.isfinite(value) for value in levels):
            raise RuntimeError("non-finite physical state")
        self.state = PlantState(tuple(levels), (inlet, flow12, flow23, outlet))  # type: ignore[arg-type]
        self._history.append(self.state.levels)
        return self.state

