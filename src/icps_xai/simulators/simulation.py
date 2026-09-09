"""Closed-loop campaign and plant execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..core.campaign import CampaignValidator
from ..core.domain import AttackStage, Campaign, Observation, ResponseAction, Trace, TraceStep
from ..models.plant import ThreeStageWaterPlant
from ..models.responder import FrozenResponder, QLearningResponder, StateKey


class ActingPolicy(Protocol):
    def reset(self) -> None: ...
    def act(self, observation: Observation) -> ResponseAction: ...


@dataclass(frozen=True)
class SimulationConfig:
    horizon: int = 100
    high_fidelity: bool = False
    response_costs: tuple[float, float, float, float] = (0.0, 0.3, 1.2, 3.0)
    switching_cost: float = 0.01


class ICPSSimulator:
    def __init__(self, config: SimulationConfig | None = None) -> None:
        self.config = config or SimulationConfig()
        self.validator = CampaignValidator()

    @staticmethod
    def _active(campaign: Campaign, stage: AttackStage, time: int) -> float:
        for event in campaign.events:
            if event.stage is stage and event.time <= time < event.time + event.duration:
                return event.magnitude
        return 0.0

    @staticmethod
    def _active_asset(campaign: Campaign, stage: AttackStage, time: int) -> str | None:
        for event in campaign.events:
            if event.stage is stage and event.time <= time < event.time + event.duration:
                return event.asset
        return None

    @staticmethod
    def _visible(campaign: Campaign, stage: AttackStage, time: int) -> float:
        for event in campaign.events:
            if event.stage is stage and event.time <= time < event.time + event.duration:
                return min(1.0, event.magnitude * event.visibility)
        return 0.0

    @staticmethod
    def _stage(campaign: Campaign, time: int) -> AttackStage | None:
        active = [event.stage for event in campaign.events if event.time <= time < event.time + event.duration]
        return max(active) if active else None

    def _observation(
        self,
        plant: ThreeStageWaterPlant,
        campaign: Campaign,
        time: int,
        previous_action: ResponseAction,
    ) -> Observation:
        replay = self._active(campaign, AttackStage.MEASUREMENT_REPLAY, time)
        replay_asset = self._active_asset(campaign, AttackStage.MEASUREMENT_REPLAY, time)
        replay_sensor = {
            "level_sensor_1": 0,
            "level_sensor_2": 1,
        }.get(replay_asset)
        delivered = plant.delivered_levels(
            replay_strength=min(0.94, 0.80 * replay), replay_sensor=replay_sensor
        )
        residual = max(abs(actual - observed) for actual, observed in zip(plant.state.levels, delivered))
        auth = max(
            self._visible(campaign, AttackStage.CREDENTIAL_ACCESS, time),
            self._visible(campaign, AttackStage.ENGINEERING_ACCESS, time),
        )
        discovery = self._visible(campaign, AttackStage.PLC_DISCOVERY, time)
        historian = self._visible(campaign, AttackStage.HISTORIAN_IMPAIRMENT, time)
        write = 0.55 * self._visible(campaign, AttackStage.ACTUATOR_OVERRIDE, time)
        availability = 1.0 - (0.04, 0.08, 0.22, 0.30)[int(previous_action)]
        return Observation(
            delivered,
            plant.state.flows,
            auth,
            discovery,
            historian,
            write,
            residual,
            availability,
            previous_action,
        )

    def _reward(
        self,
        state_levels: tuple[float, float, float],
        attack: float,
        action: ResponseAction,
        previous_action: ResponseAction,
    ) -> float:
        deviation = sum(abs(level - target) for level, target in zip(state_levels, (0.66, 0.62, 0.58)))
        outside = sum(not (0.20 <= level <= 1.12) for level in state_levels)
        mitigation = (0.0, 0.12, 0.60, 1.0)[int(action)]
        residual_attack = attack * (1.0 - mitigation)
        return -(
            7.0 * deviation
            + 30.0 * outside
            + 2.8 * residual_attack
            + self.config.response_costs[int(action)]
            + self.config.switching_cost * float(action is not previous_action)
        )

    def run(self, campaign: Campaign, policy: ActingPolicy, seed: int = 0) -> Trace:
        validity = self.validator.validate(campaign, self.config.horizon)
        if not validity.valid:
            raise ValueError("invalid campaign: " + "; ".join(validity.errors))
        plant = ThreeStageWaterPlant(seed, self.config.high_fidelity)
        plant.reset()
        policy.reset()
        previous_action = ResponseAction.MONITOR
        steps: list[TraceStep] = []
        for time in range(self.config.horizon):
            observation = self._observation(plant, campaign, time, previous_action)
            action = policy.act(observation)
            attack = self._active(campaign, AttackStage.ACTUATOR_OVERRIDE, time)
            attack_asset = self._active_asset(campaign, AttackStage.ACTUATOR_OVERRIDE, time)
            state = plant.step(observation.delivered_levels, attack, attack_asset, action)
            reward = self._reward(state.levels, attack, action, previous_action)
            steps.append(TraceStep(time, state, observation, action, self._stage(campaign, time), attack, reward))
            previous_action = action
        return Trace(campaign, tuple(steps))

    def train_episode(
        self,
        campaign: Campaign,
        learner: QLearningResponder,
        seed: int,
        epsilon: float,
    ) -> float:
        validity = self.validator.validate(campaign, self.config.horizon)
        if not validity.valid:
            raise ValueError("invalid training campaign")
        plant = ThreeStageWaterPlant(seed, self.config.high_fidelity)
        plant.reset()
        learner.reset()
        previous_action = ResponseAction.MONITOR
        previous_transition: tuple[StateKey, ResponseAction, float] | None = None
        total = 0.0
        for time in range(self.config.horizon):
            observation = self._observation(plant, campaign, time, previous_action)
            state_key = learner.encode(observation)
            if previous_transition is not None:
                old_state, old_action, old_reward = previous_transition
                learner.update(old_state, old_action, old_reward, state_key)
            action = learner.select(state_key, epsilon)
            attack = self._active(campaign, AttackStage.ACTUATOR_OVERRIDE, time)
            attack_asset = self._active_asset(campaign, AttackStage.ACTUATOR_OVERRIDE, time)
            state = plant.step(observation.delivered_levels, attack, attack_asset, action)
            reward = self._reward(state.levels, attack, action, previous_action)
            previous_transition = state_key, action, reward
            previous_action = action
            total += reward
        if previous_transition is not None:
            learner.update(*previous_transition, None)
        return total


def ensure_frozen(policy: FrozenResponder | QLearningResponder) -> FrozenResponder:
    return policy.freeze() if isinstance(policy, QLearningResponder) else policy
