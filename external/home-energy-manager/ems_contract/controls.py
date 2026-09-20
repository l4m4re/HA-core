"""Growatt actuator metadata for a future, separate EMS executor."""

from dataclasses import dataclass
from enum import StrEnum


class ActuatorClass(StrEnum):
    """HA-8A actuator classes."""

    FAST_RUNTIME = "fast_runtime"
    SLOW_OPERATIONAL = "slow_operational"
    PERSISTENT_OR_UNKNOWN = "persistent_or_unknown"


@dataclass(frozen=True)
class GrowattControlMetadata:
    """Write-policy metadata without a device endurance assumption."""

    control_id: str
    registers: tuple[int, ...]
    actuator_class: ActuatorClass = ActuatorClass.PERSISTENT_OR_UNKNOWN
    writable: bool = True
    write_on_change_required: bool = True
    verify_readback_required: bool = True
    minimum_cadence_ms: int | None = None
    evidence: str = "HA-8A; persistent behaviour not yet validated"


GROWATT_XH_CONTROLS = (
    GrowattControlMetadata("inverter_power_control", (0,)),
    GrowattControlMetadata("grid_first_discharge_rate", (3036,)),
    GrowattControlMetadata("grid_first_stop_soc", (3037,)),
    GrowattControlMetadata("xh_schedule", tuple(range(3038, 3060))),
    GrowattControlMetadata("battery_first_charge_rate", (3047,)),
    GrowattControlMetadata("battery_first_stop_soc", (3048,)),
    GrowattControlMetadata("ac_charge_enabled", (3049,)),
    GrowattControlMetadata("load_first_stop_soc", (3082,)),
)
