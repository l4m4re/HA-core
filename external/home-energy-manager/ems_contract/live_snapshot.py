"""Load a bounded live-input fixture into the HA-8B snapshot contract."""

from collections.abc import Mapping
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .growatt import decode_priority_word, decode_xh_schedule
from .providers import EvAvailability, EvProviderState, PriceProviderState
from .snapshot import EmsSnapshot, GrowattState


def _timestamp(value: str | None) -> datetime | None:
    """Parse an optional JSON timestamp."""

    return datetime.fromisoformat(value) if value else None


def snapshot_from_inventory(inventory: Mapping[str, Any]) -> EmsSnapshot:
    """Build a pure snapshot from the sanitized HA-8C inventory artifact."""

    snapshot_data = inventory["snapshot"]
    feedback = snapshot_data["growatt_feedback"]
    telemetry = snapshot_data.get("growatt_telemetry", {})
    raw_registers = {
        int(register): value
        for register, value in feedback["schedule_registers"].items()
    }
    priority = decode_priority_word(feedback["current_priority"]["raw_value"])
    schedule = decode_xh_schedule(raw_registers)

    price = PriceProviderState(
        current=None,
        future=(),
        retrieved_at=None,
        valid=False,
        error_reason="not_configured",
    )
    ev = EvProviderState(
        availability=EvAvailability.UNAVAILABLE,
        observed_at=None,
        valid=False,
        error_reason="no_vehicle_soc_provider_configured",
    )
    observed_at = _timestamp(snapshot_data["observed_at"])
    return EmsSnapshot(
        timestamp=_timestamp(inventory["captured_at"]) or observed_at,
        growatt=GrowattState(
            observed_at=observed_at,
            current_priority=priority,
            schedule=schedule,
            grid_import_power_w=telemetry.get("grid_import_power_w"),
            grid_export_power_w=telemetry.get("grid_export_power_w"),
            house_load_power_w=telemetry.get("house_load_power_w"),
            pv_power_w=telemetry.get("pv_power_w"),
            battery_power_w=telemetry.get("battery_power_w"),
            battery_soc_pct=telemetry.get("battery_soc_pct"),
            telemetry_valid=bool(telemetry.get("telemetry_valid", False)),
            priority_observed_at=_timestamp(feedback["observed_at"]),
            schedule_observed_at=_timestamp(feedback["observed_at"]),
        ),
        price=price,
        ev=ev,
    )


def load_snapshot(path: str | Path) -> EmsSnapshot:
    """Load the checked-in live-input inventory without contacting a device."""

    with Path(path).open(encoding="utf-8") as inventory_file:
        return snapshot_from_inventory(json.load(inventory_file))
