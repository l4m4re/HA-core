"""Read-only normalized EMS input state."""

from dataclasses import dataclass
from datetime import datetime

from .growatt import PriorityWord, XhScheduleSlot
from .providers import EvProviderState, PriceProviderState


@dataclass(frozen=True)
class GrowattState:
    """Growatt measurements and feedback without planner decisions."""

    observed_at: datetime | None
    current_priority: PriorityWord | None = None
    schedule: tuple[XhScheduleSlot, ...] = ()
    grid_import_power_w: float | None = None
    grid_export_power_w: float | None = None
    house_load_power_w: float | None = None
    pv_power_w: float | None = None
    battery_power_w: float | None = None
    battery_soc_pct: float | None = None
    telemetry_valid: bool = False
    priority_observed_at: datetime | None = None
    schedule_observed_at: datetime | None = None


@dataclass(frozen=True)
class EmsSnapshot:
    """Pure read-only input to the future HA-8C planner."""

    timestamp: datetime
    growatt: GrowattState
    price: PriceProviderState | None = None
    ev: EvProviderState | None = None
