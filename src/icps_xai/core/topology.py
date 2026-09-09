"""Commissioned cyber topology and campaign-stage prerequisites."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .domain import AttackStage


class Privilege(IntEnum):
    NONE = 0
    USER = 1
    ENGINEER = 2
    CONTROL = 3


@dataclass(frozen=True)
class StageRule:
    required_privilege: Privilege
    granted_privilege: Privilege
    allowed_sources: frozenset[str]


DEFAULT_EDGES = frozenset(
    {
        ("external", "vpn"),
        ("external", "jump_host"),
        ("vpn", "engineering_workstation"),
        ("jump_host", "engineering_workstation"),
        ("engineering_workstation", "historian"),
        ("engineering_workstation", "plc1"),
        ("engineering_workstation", "plc2"),
        ("engineering_workstation", "plc3"),
        ("historian", "level_sensor_1"),
        ("historian", "level_sensor_2"),
        ("plc1", "level_sensor_1"),
        ("plc2", "level_sensor_1"),
        ("plc2", "level_sensor_2"),
        ("plc2", "inlet_valve"),
        ("plc2", "transfer_pump"),
        ("plc3", "level_sensor_2"),
    }
)


STAGE_RULES: dict[AttackStage, StageRule] = {
    AttackStage.CREDENTIAL_ACCESS: StageRule(
        Privilege.NONE, Privilege.USER, frozenset({"external"})
    ),
    AttackStage.ENGINEERING_ACCESS: StageRule(
        Privilege.USER, Privilege.ENGINEER, frozenset({"vpn", "jump_host"})
    ),
    AttackStage.PLC_DISCOVERY: StageRule(
        Privilege.ENGINEER, Privilege.CONTROL, frozenset({"engineering_workstation"})
    ),
    AttackStage.HISTORIAN_IMPAIRMENT: StageRule(
        Privilege.ENGINEER,
        Privilege.CONTROL,
        frozenset({"engineering_workstation", "plc1", "plc2", "plc3"}),
    ),
    AttackStage.MEASUREMENT_REPLAY: StageRule(
        Privilege.CONTROL,
        Privilege.CONTROL,
        frozenset({"historian", "plc1", "plc2", "plc3"}),
    ),
    AttackStage.ACTUATOR_OVERRIDE: StageRule(
        Privilege.CONTROL, Privilege.CONTROL, frozenset({"plc1", "plc2", "plc3"})
    ),
}


@dataclass(frozen=True)
class CyberTopology:
    """Directed conduits used by the independent campaign validator."""

    edges: frozenset[tuple[str, str]] = DEFAULT_EDGES

    def directly_reachable(self, source: str, target: str) -> bool:
        return (source, target) in self.edges

    def valid_sources(
        self,
        target: str,
        footholds: dict[str, Privilege],
        rule: StageRule,
    ) -> tuple[str, ...]:
        return tuple(
            source
            for source, privilege in footholds.items()
            if source in rule.allowed_sources
            and privilege >= rule.required_privilege
            and self.directly_reachable(source, target)
        )
