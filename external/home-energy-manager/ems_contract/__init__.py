"""Project-independent read-only contracts for the future Home Energy Manager."""

from .growatt import (
    PriorityMode,
    PriorityWord,
    XhScheduleSlot,
    decode_priority_word,
    decode_xh_schedule,
)
from .live_snapshot import load_snapshot, snapshot_from_inventory
from .planner import (
    CrossSourceDiagnostic,
    GridObservation,
    PlannerConfig,
    PlannerReason,
    ShadowMode,
    ShadowPlan,
    cross_source_balance,
    plan_shadow_ems,
)
from .providers import (
    EvAvailability,
    EvProvider,
    EvProviderState,
    FixtureEvProvider,
    FixturePriceProvider,
    PriceInterval,
    PriceProvider,
    PriceProviderState,
)
from .snapshot import EmsSnapshot, GrowattState
from .zonneplan import parse_zonneplan_entity

__all__ = [
    "CrossSourceDiagnostic",
    "EmsSnapshot",
    "EvAvailability",
    "EvProvider",
    "EvProviderState",
    "FixtureEvProvider",
    "FixturePriceProvider",
    "GridObservation",
    "GrowattState",
    "PlannerConfig",
    "PlannerReason",
    "PriceInterval",
    "PriceProvider",
    "PriceProviderState",
    "PriorityMode",
    "PriorityWord",
    "ShadowMode",
    "ShadowPlan",
    "XhScheduleSlot",
    "cross_source_balance",
    "decode_priority_word",
    "decode_xh_schedule",
    "load_snapshot",
    "parse_zonneplan_entity",
    "plan_shadow_ems",
    "snapshot_from_inventory",
]
