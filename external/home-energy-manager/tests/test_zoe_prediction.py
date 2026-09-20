"""Replay-based Zoe charging-rate model tests."""

from datetime import datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from ems_contract.providers import PriceBasis
from ems_contract.zoe_prediction import (
    ZoeChargeWindow,
    estimate_charge_duration_hours,
    fit_charge_rate_model,
    load_poller_csv,
    plan_price_aware_charge,
    project_charge_session,
    split_charge_sessions,
)
from ems_contract.zonneplan import parse_zonneplan_entity

FIXTURES = Path(__file__).parent / "fixtures"
TRAINING_DATA = (
    Path(__file__).parents[1] / "ems_contract/data/zoe/charge_replay_training.csv"
)


def test_charge_rate_model_fits_replay_sessions_by_soc_band() -> None:
    """The rate estimate preserves the measured current and SoC band."""

    samples = load_poller_csv(TRAINING_DATA)
    model = fit_charge_rate_model(samples)

    estimate = next(
        item for item in model if item.current_setting_a == 13 and item.band == "middle"
    )
    assert estimate.training_sessions >= 8
    assert estimate.training_hours >= 20
    assert 5.5 < estimate.rate_pct_per_hour < 7.5
    assert estimate.mean_power_w is not None
    assert estimate.confidence == "high"


def test_poller_state_marks_charging_when_capture_lacks_boolean_column(
    tmp_path: Path,
) -> None:
    """Current PyCanZE captures identify charging in the state column."""

    capture = tmp_path / "pycanze.csv"
    capture.write_text(
        "timestamp,state,soc,shelly_current_a,shelly_apower_w\n"
        "2026-01-01T00:00:00,charging,40,12.4,2700\n"
        "2026-01-01T00:05:00,awake,40.5,0,0\n",
        encoding="utf-8",
    )

    samples = load_poller_csv(capture)

    assert [sample.charging for sample in samples] == [True, False]
    assert samples[0].soc_pct == 40
    assert samples[0].current_a == 12.4


def test_holdout_capture_durations_are_predicted_from_other_sessions() -> None:
    """A separate PyCanZE capture validates the target range up to 80% SoC."""

    training = load_poller_csv(TRAINING_DATA)
    held_out_sessions = split_charge_sessions(
        load_poller_csv(FIXTURES / "zoe_charge_holdout.csv")
    )
    model = fit_charge_rate_model(training)
    predictions = tuple(
        estimate_charge_duration_hours(
            model,
            initial_soc_pct=cast(float, session[0].soc_pct),
            target_soc_pct=cast(float, session[-1].soc_pct),
            current_setting_a=13,
        )
        for session in held_out_sessions
    )
    observations = tuple(
        (session[-1].timestamp - session[0].timestamp).total_seconds() / 3600
        for session in held_out_sessions
    )

    assert len(held_out_sessions) >= 8
    assert all(
        sample.soc_pct is not None
        for session in held_out_sessions
        for sample in session
    )
    assert all(prediction is not None for prediction in predictions)
    relative_errors = tuple(
        abs(prediction - observed) / observed
        for prediction, observed in zip(predictions, observations, strict=True)
        if prediction is not None
    )
    assert max(relative_errors) < 0.15


def test_projection_returns_soc_curve_and_charge_energy() -> None:
    """The replay model projects only during the supplied charge windows."""

    model = fit_charge_rate_model(load_poller_csv(TRAINING_DATA))
    start = datetime(2026, 9, 18, 22, tzinfo=ZoneInfo("Europe/Amsterdam"))
    projection = project_charge_session(
        model,
        (ZoeChargeWindow(start, start + timedelta(hours=8)),),
        initial_soc_pct=50,
        target_soc_pct=80,
        current_setting_a=13,
    )

    assert projection.valid
    assert projection.predicted_finish is not None
    assert start < projection.predicted_finish < start + timedelta(hours=8)
    assert projection.projected_grid_energy_kwh is not None
    assert projection.projected_grid_energy_kwh > 0
    assert all(
        point.slow_soc_pct <= point.soc_pct <= point.fast_soc_pct
        for point in projection.points
    )
    json.dumps(projection.as_dict())


def test_price_aware_zoe_schedule_uses_cheapest_intervals_before_departure() -> None:
    """Zoe charging is planned from measured rates and the all-in forecast."""

    training = load_poller_csv(TRAINING_DATA)
    model = fit_charge_rate_model(training)
    price_fixture_path = FIXTURES / "ha8d_zonneplan_quarter_hour.json"
    price_fixture = json.loads(price_fixture_path.read_text(encoding="utf-8"))
    now = datetime.fromisoformat("2026-09-06T17:08:00+02:00")
    earliest_start = datetime.fromisoformat("2026-09-06T17:15:00+02:00")
    departure = datetime.fromisoformat("2026-09-06T22:30:00+02:00")
    prices = parse_zonneplan_entity(
        price_fixture["entity"],
        now=now,
        retrieved_at=datetime.fromisoformat(price_fixture["retrieved_at"]),
        timezone_name=price_fixture["timezone"],
    )

    schedule = plan_price_aware_charge(
        model,
        prices,
        now=now,
        earliest_start=earliest_start,
        departure=departure,
        initial_soc_pct=50,
        target_soc_pct=80,
        current_setting_a=13,
    )

    assert schedule.valid
    assert schedule.required_duration_hours is not None
    selected_hours = sum(
        (interval.end - interval.start).total_seconds() / 3600
        for interval in schedule.selected_intervals
    )
    assert selected_hours >= schedule.required_duration_hours
    assert all(
        earliest_start <= interval.start and interval.end <= departure
        for interval in schedule.selected_intervals
    )
    available = tuple(
        sorted(
            (
                interval
                for interval in prices.future
                if earliest_start <= interval.start and interval.end <= departure
            ),
            key=lambda interval: interval.start,
        )
    )
    earliest_slots = available[: len(schedule.selected_intervals)]
    selected_prices = tuple(
        interval.import_price for interval in schedule.selected_intervals
    )
    earliest_prices = tuple(interval.import_price for interval in earliest_slots)
    assert all(price is not None for price in (*selected_prices, *earliest_prices))
    assert sum(
        (price for price in selected_prices if price is not None), Decimal(0)
    ) < sum((price for price in earliest_prices if price is not None), Decimal(0))
    assert schedule.price_basis == PriceBasis.ALL_IN_IMPORT.value
    assert schedule.estimated_import_cost_eur is not None
    assert schedule.estimated_import_cost_eur > 0
    assert schedule.windows
    projection = project_charge_session(
        model,
        schedule.windows,
        initial_soc_pct=50,
        target_soc_pct=80,
        current_setting_a=13,
    )
    assert projection.valid
    assert projection.predicted_finish is not None
    assert projection.predicted_finish <= departure


def test_missing_rate_data_is_explicitly_unavailable() -> None:
    """No replay samples do not become a made-up Zoe charge rate."""

    projection = project_charge_session(
        (),
        (
            ZoeChargeWindow(
                datetime(2026, 9, 18, 22, tzinfo=ZoneInfo("Europe/Amsterdam")),
                datetime(2026, 9, 19, 6, tzinfo=ZoneInfo("Europe/Amsterdam")),
            ),
        ),
        initial_soc_pct=50,
        target_soc_pct=80,
        current_setting_a=13,
    )

    assert not projection.valid
    assert projection.predicted_finish is None
    assert projection.confidence == "unavailable"
    assert projection.warnings == ("invalid_projection_inputs",)
