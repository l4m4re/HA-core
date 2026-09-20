"""HA-8C live inventory adapter tests."""

from pathlib import Path

from ems_contract import EvAvailability, load_snapshot

INVENTORY = Path(__file__).parents[1] / "docs/HA-8C_LIVE_INPUT_INVENTORY.json"


def test_live_inventory_uses_typed_growatt_feedback() -> None:
    """The sanitized live fixture is decoded through the HA-8B types."""

    snapshot = load_snapshot(INVENTORY)

    assert snapshot.growatt.current_priority is not None
    assert snapshot.growatt.current_priority.state == "load_first"
    assert snapshot.growatt.current_priority.raw == 0
    assert len(snapshot.growatt.schedule) == 9
    assert snapshot.growatt.schedule[1].start.isoformat(timespec="minutes") == "00:00"
    assert snapshot.growatt.schedule[1].enabled
    assert not snapshot.growatt.schedule[0].enabled
    assert snapshot.growatt.telemetry_valid


def test_live_inventory_preserves_missing_provider_values() -> None:
    """Missing price and EV inputs remain unavailable rather than zero."""

    snapshot = load_snapshot(INVENTORY)

    assert snapshot.price is not None
    assert not snapshot.price.valid
    assert snapshot.price.current is None
    assert snapshot.ev is not None
    assert snapshot.ev.availability is EvAvailability.UNAVAILABLE
    assert snapshot.ev.soc_pct is None
