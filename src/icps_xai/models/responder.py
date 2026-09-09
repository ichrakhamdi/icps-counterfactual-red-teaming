"""Independent flat Q-learning responder used as the XAI audit target."""

from __future__ import annotations

import json
import hashlib
import random
from pathlib import Path

from ..core.domain import Observation, ResponseAction


StateKey = tuple[int, int, int, int]


class EvidenceEncoder:
    """Compress observations using a generic exponentially weighted memory."""

    def __init__(self) -> None:
        self.evidence_memory = 0.0

    def reset(self) -> None:
        self.evidence_memory = 0.0

    def encode(self, observation: Observation) -> StateKey:
        self.evidence_memory = 0.84 * self.evidence_memory + 0.16 * observation.evidence()
        risk_bin = min(4, int(self.evidence_memory * 5.0))
        deviation = max(abs(level - target) for level, target in zip(observation.delivered_levels, (0.66, 0.62, 0.58)))
        physical_bin = 0 if deviation < 0.06 else 1 if deviation < 0.14 else 2
        integrity_bin = int(max(observation.historian_gap, observation.controller_write_alert) >= 0.35)
        return risk_bin, physical_bin, integrity_bin, int(observation.previous_action)


class QLearningResponder:
    """Small, architecture-independent responder with a discrete action set."""

    actions = tuple(ResponseAction)

    def __init__(
        self,
        seed: int = 0,
        learning_rate: float = 0.12,
        discount: float = 0.97,
    ) -> None:
        self.rng = random.Random(seed)
        self.learning_rate = learning_rate
        self.discount = discount
        self.encoder = EvidenceEncoder()
        self.q: dict[StateKey, list[float]] = {}

    def reset(self) -> None:
        self.encoder.reset()

    def encode(self, observation: Observation) -> StateKey:
        return self.encoder.encode(observation)

    def values(self, state: StateKey) -> list[float]:
        return self.q.setdefault(state, [0.0 for _ in self.actions])

    def select(self, state: StateKey, epsilon: float = 0.0) -> ResponseAction:
        if self.rng.random() < epsilon:
            return self.rng.choice(self.actions)
        values = self.values(state)
        best = max(values)
        return ResponseAction(next(index for index, value in enumerate(values) if value == best))

    def update(
        self,
        state: StateKey,
        action: ResponseAction,
        reward: float,
        next_state: StateKey | None,
    ) -> None:
        values = self.values(state)
        bootstrap = 0.0 if next_state is None else max(self.values(next_state))
        target = reward + self.discount * bootstrap
        index = int(action)
        values[index] += self.learning_rate * (target - values[index])

    def freeze(self) -> "FrozenResponder":
        return FrozenResponder({key: tuple(values) for key, values in self.q.items()})

    def save(self, path: Path) -> None:
        rows = [
            {"state": list(key), "values": values}
            for key, values in sorted(self.q.items())
        ]
        path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


class FrozenResponder:
    """Read-only black-box interface exposed to the explanation engine."""

    def __init__(self, q: dict[StateKey, tuple[float, ...]]) -> None:
        self.__q = dict(q)
        self.encoder = EvidenceEncoder()

    def reset(self) -> None:
        self.encoder.reset()

    def clone(self) -> "FrozenResponder":
        """Return an independent stateful wrapper around the same frozen table."""

        return FrozenResponder(dict(self.__q))

    def digest(self) -> str:
        """Stable identifier used to prove that explanation does not alter the policy."""

        rows = [(list(key), list(values)) for key, values in sorted(self.__q.items())]
        encoded = json.dumps(rows, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def act(self, observation: Observation) -> ResponseAction:
        state = self.encoder.encode(observation)
        values = self.__q.get(state)
        if values is None:
            # Conservative generic fallback for states absent from training.
            risk_bin, physical_bin, integrity_bin, _ = state
            score = risk_bin + physical_bin + integrity_bin
            return ResponseAction(min(3, max(0, score // 2)))
        best = max(values)
        return ResponseAction(next(index for index, value in enumerate(values) if value == best))
