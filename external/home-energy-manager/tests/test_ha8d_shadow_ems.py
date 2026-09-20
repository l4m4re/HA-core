"""HA-8D Zonneplan adapter and shadow planner tests."""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from ems_contract.growatt import decode_priority_word, decode_xh_schedule
from ems_contract.live_snapshot import load_snapshot
from ems_contract.planner import (
    GridObservation,
    PlannerConfig,
    PlannerReason,
    ShadowMode,
    cross_source_balance,
    plan_shadow_ems,
)
from ems_contract.providers import PriceBasis, PriceInterval, PriceProviderState
from ems_contract.zonneplan import parse_zonneplan_entity

ROOT = Path(__file__).parents[1]
INVENTORY = ROOT / "docs/HA-8C_LIVE_INPUT_INVENTORY.json"
PRICE_FIXTURE = ROOT / "tests/fixtures/ha8d_zonneplan_quarter_hour.json"


def _snapshot():
    return load_snapshot(INVENTORY)


def _price_fixture() -> dict:
    with PRICE_FIXTURE.open(encoding="utf-8") as price_file:
        return json.load(price_file)


def _prices(snapshot):
    fixture = _price_fixture()
    return parse_zonneplan_entity(
        fixture["entity"],
        now=snapshot.timestamp,
        retrieved_at=datetime.fromisoformat(fixture["retrieved_at"]),
        timezone_name=fixture["timezone"],
    )


def _config(**changes):
    values = {
        "required_forecast_horizon": timedelta(hours=4),
    }
    values.update(changes)
    return replace(PlannerConfig(), **values)


def test_zonneplan_adapter_uses_quarter_hour_all_in_price() -> None:
    """The upstream fixed-point tax-included field becomes import price."""

    state = _prices(_snapshot())

    assert state.valid
    assert state.current is not None
    assert state.current.start.isoformat() == "2026-09-06T17:00:00+02:00"
    assert state.current.import_price == Decimal("0.3")
    assert state.current.price_basis is PriceBasis.ALL_IN_IMPORT
    assert state.current.tax_excluded_price == Decimal("0.25")
    assert state.current.export_price is None
    assert len(state.future) == 21


def test_zonneplan_adapter_accepts_live_datetime_attributes() -> None:
    """HA stores Zonneplan forecast timestamps as aware datetime objects."""

    snapshot = _snapshot()
    fixture = _price_fixture()
    for item in fixture["entity"]["attributes"]["forecast"]:
        item["start_date"] = datetime.fromisoformat(item["start_date"])
        item["end_date"] = datetime.fromisoformat(item["end_date"])

    state = parse_zonneplan_entity(
        fixture["entity"],
        now=snapshot.timestamp,
        retrieved_at=datetime.fromisoformat(fixture["retrieved_at"]),
    )

    assert state.valid
    assert state.current is not None
    assert state.current.price_basis is PriceBasis.ALL_IN_IMPORT


def test_zonneplan_adapter_rejects_missing_gap_and_unavailable_data() -> None:
    """Malformed or unavailable provider state cannot become valid prices."""

    snapshot = _snapshot()
    fixture = _price_fixture()
    missing = deepcopy(fixture["entity"])
    missing["attributes"] = {}
    assert (
        parse_zonneplan_entity(
            missing,
            now=snapshot.timestamp,
            retrieved_at=snapshot.timestamp,
        ).error_reason
        == "forecast_missing"
    )

    gap = deepcopy(fixture["entity"])
    gap["attributes"]["forecast"].pop(3)
    assert (
        parse_zonneplan_entity(
            gap,
            now=snapshot.timestamp,
            retrieved_at=snapshot.timestamp,
        ).error_reason
        == "forecast_gap_or_overlap"
    )

    unavailable = {"state": "unavailable", "attributes": {}}
    assert (
        parse_zonneplan_entity(
            unavailable,
            now=snapshot.timestamp,
            retrieved_at=snapshot.timestamp,
        ).error_reason
        == "provider_unavailable"
    )


def test_zonneplan_adapter_rejects_naive_timestamps_and_expired_forecast() -> None:
    """Timezone-naive and wholly expired data do not enter the planner."""

    snapshot = _snapshot()
    fixture = _price_fixture()
    naive = deepcopy(fixture["entity"])
    naive["attributes"]["forecast"][0]["start_date"] = "2026-09-06T17:00:00"
    assert (
        parse_zonneplan_entity(
            naive,
            now=snapshot.timestamp,
            retrieved_at=snapshot.timestamp,
        ).error_reason
        == "timestamp_naive"
    )

    expired = deepcopy(fixture["entity"])
    expired["attributes"]["forecast"] = [expired["attributes"]["forecast"][0]]
    expired["attributes"]["forecast"][0]["start_date"] = "2025-09-06T17:00:00+02:00"
    expired["attributes"]["forecast"][0]["end_date"] = "2025-09-06T17:15:00+02:00"
    assert (
        parse_zonneplan_entity(
            expired,
            now=snapshot.timestamp,
            retrieved_at=snapshot.timestamp,
        ).error_reason
        == "forecast_expired"
    )


def test_live_inventory_produces_reproducible_shadow_plan() -> None:
    """HA-8C live state plus deterministic quarter-hour prices is explainable."""

    plan = plan_shadow_ems(_snapshot(), _config(), price=_prices(_snapshot()))

    assert plan.valid
    assert plan.mode is ShadowMode.CHEAP_CHARGE
    assert plan.current_soc == Decimal("10.0")
    assert plan.required_energy_kwh == Decimal("7.0")
    assert len(plan.selected_cheap_intervals) == 11
    assert len(plan.growatt_candidate_windows) == 1
    assert (
        plan.growatt_candidate_windows[0].start.isoformat()
        == "2026-09-06T19:00:00+02:00"
    )
    assert (
        plan.growatt_candidate_windows[0].end.isoformat() == "2026-09-06T21:45:00+02:00"
    )
    assert plan.hypothetical_write_count == 3
    assert plan.export_optimization_enabled is False
    assert plan.boundary_semantics_unvalidated
    assert plan.battery_economics is not None
    assert plan.battery_economics.grid_energy_kwh == Decimal("8.25")
    assert plan.battery_economics.stored_energy_kwh == Decimal("7.5900")
    assert plan.battery_economics.conversion_loss_kwh == Decimal("0.6600")
    assert plan.battery_economics.wear_cost_eur == Decimal("0.379500")
    assert "battery_wear_cost_is_provisional" in plan.warnings
    assert plan.as_dict()["battery_economics"]["wear_assumption"] == (
        "provisional_example_not_device_specific"
    )


def test_battery_economics_cover_full_quarter_hour_schedule() -> None:
    """Cost the whole interval-rounded schedule and expose its energy margin."""
    snapshot = _snapshot()
    snapshot = replace(
        snapshot,
        growatt=replace(snapshot.growatt, battery_soc_pct=64),
    )

    plan = plan_shadow_ems(snapshot, _config(), price=_prices(snapshot))

    assert plan.required_energy_kwh == Decimal("1.6")
    assert len(plan.selected_cheap_intervals) == 3
    assert plan.battery_economics is not None
    assert plan.battery_economics.grid_energy_kwh == Decimal("2.25")
    assert plan.battery_economics.stored_energy_kwh == Decimal("2.0700")
    assert (
        plan.battery_economics.stored_energy_kwh - plan.required_energy_kwh
        == Decimal("0.4700")
    )


def test_already_at_target_has_no_charge_intervals() -> None:
    """A full-enough battery does not select a cheap charging window."""

    snapshot = _snapshot()
    snapshot = replace(
        snapshot,
        growatt=replace(snapshot.growatt, battery_soc_pct=85),
    )
    plan = plan_shadow_ems(snapshot, _config(), price=_prices(snapshot))

    assert plan.valid
    assert not plan.selected_cheap_intervals
    assert PlannerReason.TARGET_SOC_ALREADY_REACHED.value in plan.reason_codes


def test_stale_telemetry_and_invalid_price_are_failsafe() -> None:
    """Stale inputs select no economic mode."""

    snapshot = _snapshot()
    stale = replace(
        snapshot,
        growatt=replace(
            snapshot.growatt,
            observed_at=snapshot.timestamp - timedelta(minutes=6),
        ),
    )
    stale_plan = plan_shadow_ems(stale, _config(), price=_prices(stale))
    assert stale_plan.mode is ShadowMode.FAILSAFE
    assert PlannerReason.FAILSAFE_STALE_TELEMETRY.value in stale_plan.reason_codes

    invalid_plan = plan_shadow_ems(
        snapshot,
        _config(),
        price=PriceProviderState(
            None, (), snapshot.timestamp, False, "fixture_invalid"
        ),
    )
    assert invalid_plan.mode is ShadowMode.FAILSAFE
    assert PlannerReason.FAILSAFE_INVALID_PRICE_DATA.value in invalid_plan.reason_codes


def test_unavailable_ev_does_not_block_shadow_planning_and_profit_export_is_disabled() -> (
    None
):
    """EV absence is explicit and export economics remain unavailable."""

    snapshot = _snapshot()
    assert snapshot.ev is not None and snapshot.ev.soc_pct is None
    assert plan_shadow_ems(snapshot, _config(), price=_prices(snapshot)).valid
    export_plan = plan_shadow_ems(
        snapshot,
        _config(),
        requested_mode=ShadowMode.PROFIT_EXPORT,
        price=_prices(snapshot),
    )
    assert export_plan.mode is ShadowMode.FAILSAFE
    assert PlannerReason.EXPORT_PRICE_UNAVAILABLE.value in export_plan.reason_codes
    assert not export_plan.export_optimization_enabled


def test_unknown_priority_is_preserved_and_noop_schedule_has_zero_writes() -> None:
    """Unknown feedback does not coerce, and identical desired slots are no-ops."""

    snapshot = _snapshot()
    plan = plan_shadow_ems(snapshot, _config(), price=_prices(snapshot))
    raw = {3038: 0, 3039: 0, 3040: 0, 3041: 0, 3042: 0, 3043: 0, 3044: 0, 3045: 0}
    for item, register in zip(
        plan.desired_slots,
        (3038, 3040, 3042, 3044, 3050, 3052, 3054, 3056, 3058),
        strict=False,
    ):
        raw[register] = item.raw_start_word
        raw[register + 1] = item.raw_end_word
    matching = replace(
        snapshot,
        growatt=replace(
            snapshot.growatt,
            current_priority=decode_priority_word(7),
            schedule=decode_xh_schedule(raw),
        ),
    )
    matching_plan = plan_shadow_ems(matching, _config(), price=_prices(matching))

    assert matching_plan.actual_current_priority.state == "unknown_7"
    assert matching_plan.hypothetical_write_count == 0
    assert matching_plan.skipped_no_change_count == 9


def test_scattered_cheap_intervals_are_compressed_to_nine_slots() -> None:
    """Compression merges the cheapest gaps and reports approximation."""

    snapshot = _snapshot()
    base = _prices(snapshot)
    scattered = tuple(
        replace(
            item,
            import_price=Decimal("0.01") if index % 2 == 0 else Decimal("0.90"),
        )
        for index, item in enumerate(base.future)
    )
    prices = replace(base, future=scattered)
    plan = plan_shadow_ems(snapshot, _config(), price=prices)

    assert plan.valid
    assert len(plan.economic_windows) == 11
    assert len(plan.growatt_candidate_windows) == 9
    assert plan.warnings == (
        "battery_wear_cost_is_provisional",
        "schedule_windows_are_approximated_for_slot_limit",
    )
    assert plan.compression_added_interval_count == 2
    assert plan.compression_extra_cost_eur > 0
    assert all(item.approximate for item in plan.growatt_candidate_windows)


def test_schedule_window_crossing_midnight_is_split_for_growatt() -> None:
    """A selected economic window is split at local midnight."""

    snapshot = _snapshot()
    timezone = ZoneInfo("Europe/Amsterdam")
    now = datetime(2026, 9, 6, 23, 30, tzinfo=timezone)
    snapshot = replace(
        snapshot,
        timestamp=now,
        growatt=replace(snapshot.growatt, observed_at=now),
    )
    starts = [now + timedelta(minutes=15 * index) for index in range(12)]
    prices = PriceProviderState(
        current=PriceInterval(
            start=now - timedelta(minutes=15),
            end=now,
            import_price=Decimal("0.10"),
            export_price=None,
            source="fixture",
            retrieved_at=now,
            valid=True,
            price_basis=PriceBasis.ALL_IN_IMPORT,
        ),
        future=tuple(
            PriceInterval(
                start=start,
                end=start + timedelta(minutes=15),
                import_price=Decimal("0.10"),
                export_price=None,
                source="fixture",
                retrieved_at=now,
                valid=True,
                price_basis=PriceBasis.ALL_IN_IMPORT,
            )
            for start in starts
        ),
        retrieved_at=now,
        valid=True,
    )

    plan = plan_shadow_ems(
        snapshot,
        _config(required_forecast_horizon=timedelta(hours=3)),
        price=prices,
    )

    assert plan.valid
    assert len(plan.selected_cheap_intervals) == 11
    assert len(plan.growatt_candidate_windows) == 2
    assert plan.growatt_candidate_windows[0].end == (
        plan.growatt_candidate_windows[1].start
    )
    assert plan.growatt_candidate_windows[0].start.date() != (
        plan.growatt_candidate_windows[0].end.date()
    )


def test_cross_source_balance_is_diagnostic_only() -> None:
    """P1 remains a separate billing point and produces a tolerant residual."""

    snapshot = _snapshot()
    assert snapshot.growatt.observed_at is not None
    diagnostic = cross_source_balance(
        snapshot.growatt,
        GridObservation(2540.0, 0.0, snapshot.growatt.observed_at),
    )

    assert diagnostic.informative
    assert diagnostic.residual_w == -31.90000000000009


def test_negative_all_in_price_is_preserved() -> None:
    """Negative all-in prices are ordinary ordered prices, not a special case."""

    snapshot = _snapshot()
    fixture = _price_fixture()
    fixture["entity"]["attributes"]["forecast"][8]["price_tax_included"][
        "amount"
    ] = -1000000
    prices = parse_zonneplan_entity(
        fixture["entity"],
        now=snapshot.timestamp,
        retrieved_at=snapshot.timestamp,
    )

    assert prices.valid
    assert prices.future[7].import_price == Decimal("-0.1")


def test_dst_offsets_remain_aware() -> None:
    """Explicit offset timestamps survive Amsterdam DST transitions."""

    transition = datetime(2026, 10, 25, 0, 45, tzinfo=UTC)
    fixture = {
        "state": "0.1",
        "attributes": {
            "forecast": [
                {
                    "start_date": "2026-10-25T02:45:00+02:00",
                    "end_date": "2026-10-25T03:00:00+01:00",
                    "price_tax_included": {"amount": 1000000},
                    "price_tax_excluded": {"amount": 500000},
                },
                {
                    "start_date": "2026-10-25T03:00:00+01:00",
                    "end_date": "2026-10-25T03:15:00+01:00",
                    "price_tax_included": {"amount": 1100000},
                    "price_tax_excluded": {"amount": 600000},
                },
            ]
        },
    }
    state = parse_zonneplan_entity(
        fixture,
        now=transition,
        retrieved_at=transition,
    )

    assert state.valid
    assert state.current is not None
    assert state.current.start.tzinfo is not None
