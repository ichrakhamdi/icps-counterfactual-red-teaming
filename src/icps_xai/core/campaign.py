"""Campaign grammar, validation, and permitted edit operators."""

from __future__ import annotations

from dataclasses import dataclass

from .domain import AttackStage, Campaign, CampaignEdit, CampaignEvent
from .topology import CyberTopology, Privilege, STAGE_RULES


ASSETS_BY_STAGE: dict[AttackStage, frozenset[str]] = {
    AttackStage.CREDENTIAL_ACCESS: frozenset({"vpn", "jump_host"}),
    AttackStage.ENGINEERING_ACCESS: frozenset({"engineering_workstation"}),
    AttackStage.PLC_DISCOVERY: frozenset({"plc1", "plc2", "plc3"}),
    AttackStage.HISTORIAN_IMPAIRMENT: frozenset({"historian"}),
    AttackStage.MEASUREMENT_REPLAY: frozenset({"level_sensor_1", "level_sensor_2"}),
    AttackStage.ACTUATOR_OVERRIDE: frozenset({"inlet_valve", "transfer_pump"}),
}


DEPENDENCIES: dict[AttackStage, tuple[AttackStage, ...]] = {
    AttackStage.CREDENTIAL_ACCESS: (),
    AttackStage.ENGINEERING_ACCESS: (AttackStage.CREDENTIAL_ACCESS,),
    AttackStage.PLC_DISCOVERY: (AttackStage.ENGINEERING_ACCESS,),
    AttackStage.HISTORIAN_IMPAIRMENT: (AttackStage.PLC_DISCOVERY,),
    AttackStage.MEASUREMENT_REPLAY: (AttackStage.HISTORIAN_IMPAIRMENT,),
    AttackStage.ACTUATOR_OVERRIDE: (AttackStage.PLC_DISCOVERY,),
}


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: tuple[str, ...]


class CampaignValidator:
    """Independent validity checker; the search cannot bypass it."""

    def __init__(self, topology: CyberTopology | None = None) -> None:
        self.topology = topology or CyberTopology()

    def validate(self, campaign: Campaign, horizon: int = 100) -> ValidationResult:
        errors: list[str] = []
        present: dict[AttackStage, CampaignEvent] = {}
        for event in campaign.events:
            if event.stage in present:
                errors.append(f"duplicate stage {event.stage.name}")
            present[event.stage] = event
            if event.asset not in ASSETS_BY_STAGE[event.stage]:
                errors.append(f"asset {event.asset} is invalid for {event.stage.name}")
            if not 0 <= event.time < horizon:
                errors.append(f"event time {event.time} outside horizon")
            if not 0.0 <= event.visibility <= 1.0:
                errors.append("visibility outside [0,1]")
            if not 0.0 < event.magnitude <= 1.5:
                errors.append("magnitude outside (0,1.5]")
            if not 1 <= event.duration <= horizon:
                errors.append("duration outside horizon")
            if event.time + event.duration > horizon:
                errors.append("event extends beyond horizon")

        for stage, event in present.items():
            for dependency in DEPENDENCIES[stage]:
                required = present.get(dependency)
                if required is None:
                    errors.append(f"{stage.name} lacks {dependency.name}")
                elif required.time >= event.time:
                    errors.append(f"{dependency.name} must precede {stage.name}")

        # Replay the ordered campaign against the commissioned network. A
        # dependency can exist in time and still be unusable when no foothold
        # with enough privilege has a conduit to the target asset.
        footholds = {"external": Privilege.NONE}
        for event in sorted(campaign.events, key=lambda item: (item.time, int(item.stage))):
            rule = STAGE_RULES[event.stage]
            sources = self.topology.valid_sources(event.asset, footholds, rule)
            if not sources:
                errors.append(
                    f"{event.stage.name} cannot reach {event.asset} from an eligible foothold"
                )
            else:
                previous = footholds.get(event.asset, Privilege.NONE)
                footholds[event.asset] = max(previous, rule.granted_privilege)

        return ValidationResult(not errors, tuple(errors))


def reference_campaign(
    *,
    name: str = "reference_campaign",
    offset: int = 0,
    impact_magnitude: float = 1.0,
) -> Campaign:
    """A fixed, executable campaign used for the independent prototype."""

    events = (
        CampaignEvent(AttackStage.CREDENTIAL_ACCESS, 8 + offset, "vpn", 0.75, 0.90, 3),
        CampaignEvent(AttackStage.ENGINEERING_ACCESS, 18 + offset, "engineering_workstation", 0.80, 0.90, 3),
        CampaignEvent(AttackStage.PLC_DISCOVERY, 29 + offset, "plc2", 0.85, 0.85, 4),
        CampaignEvent(AttackStage.HISTORIAN_IMPAIRMENT, 40 + offset, "historian", 0.90, 0.90, 12),
        CampaignEvent(AttackStage.MEASUREMENT_REPLAY, 50 + offset, "level_sensor_1", 1.00, 0.80, 28),
        CampaignEvent(AttackStage.ACTUATOR_OVERRIDE, 62 + offset, "inlet_valve", impact_magnitude, 0.75, 24),
    )
    return Campaign(name, events)


def campaign_neighbors(campaign: Campaign) -> list[tuple[Campaign, CampaignEdit]]:
    """Generate local, semantically meaningful campaign edits."""

    neighbors: list[tuple[Campaign, CampaignEdit]] = []
    for index, event in enumerate(campaign.events):
        # The physical impact event is held fixed. Explanations may alter only
        # the observable preparation path leading to the audited decision.
        if event.stage is AttackStage.ACTUATOR_OVERRIDE:
            continue
        for asset in sorted(ASSETS_BY_STAGE[event.stage] - {event.asset}):
            edit = CampaignEdit(index, "asset", event.asset, asset, 1.0)
            neighbors.append(
                (campaign.with_event(index, event.edited(asset=asset), f"a{index}={asset}"), edit)
            )
        for factor in (0.75, 0.5):
            value = round(max(0.08, event.visibility * factor), 4)
            if value < event.visibility:
                edit = CampaignEdit(index, "visibility", event.visibility, value, event.visibility - value)
                neighbors.append(
                    (campaign.with_event(index, event.edited(visibility=value), f"v{index}={value}"), edit)
                )
        for factor in (0.75, 0.5):
            value = round(max(0.15, event.magnitude * factor), 4)
            if value < event.magnitude:
                edit = CampaignEdit(index, "magnitude", event.magnitude, value, event.magnitude - value)
                neighbors.append(
                    (campaign.with_event(index, event.edited(magnitude=value), f"m{index}={value}"), edit)
                )

        for shift in (-3, 3):
            value = event.time + shift
            if value >= 0:
                edit = CampaignEdit(index, "time", event.time, value, abs(shift) / 20.0)
                neighbors.append((campaign.with_event(index, event.edited(time=value), f"t{index}={value}"), edit))

        if event.stage in {AttackStage.HISTORIAN_IMPAIRMENT, AttackStage.MEASUREMENT_REPLAY}:
            value = max(3, event.duration - 4)
            if value != event.duration:
                edit = CampaignEdit(index, "duration", event.duration, value, 4 / 20.0)
                neighbors.append(
                    (campaign.with_event(index, event.edited(duration=value), f"d{index}={value}"), edit)
                )

    # A campaign-wide low-observable profile represents a consistent change in
    # attacker tradecraft. It is costed by the total visibility withdrawn from
    # all preparation stages, rather than counted as a free single edit.
    for factor in (0.75, 0.5):
        changed: list[CampaignEvent] = []
        cost = 0.0
        for event in campaign.events:
            if event.stage is AttackStage.ACTUATOR_OVERRIDE:
                changed.append(event)
                continue
            visibility = round(max(0.08, event.visibility * factor), 4)
            cost += event.visibility - visibility
            changed.append(event.edited(visibility=visibility))
        if cost > 0:
            edit = CampaignEdit(-1, "precursor_visibility_profile", 1.0, factor, cost)
            neighbors.append((Campaign(f"{campaign.name}|profile={factor}", tuple(changed)).sorted(), edit))
    return neighbors
