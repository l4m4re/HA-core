"""Dynamic price trend calculations from recorded provider states."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ems_contract.price_trends import PriceObservation, calculate_price_trends


def test_time_weighted_averages_cover_one_hour_and_full_day() -> None:
    """Quarter-hour all-in prices produce rolling and daily mean lines."""

    now = datetime(2026, 9, 18, 12, tzinfo=UTC)
    start = now - timedelta(hours=24)
    observations = tuple(
        PriceObservation(
            start + timedelta(minutes=15 * index),
            Decimal(index - 48) / Decimal(100),
        )
        for index in range(96)
    )

    trends = calculate_price_trends(observations, now=now)

    assert trends.moving_average_1h == Decimal("0.455")
    assert trends.mean_24h == Decimal("-0.005")
    assert trends.coverage_1h == timedelta(hours=1)
    assert trends.coverage_24h == timedelta(hours=24)
    assert trends.observations_24h == 96


def test_short_or_naive_history_does_not_claim_a_full_window_average() -> None:
    """Missing history coverage remains unavailable instead of being filled."""

    now = datetime(2026, 9, 18, 12, tzinfo=UTC)
    observations = (
        PriceObservation(now - timedelta(minutes=30), Decimal("-0.05")),
        PriceObservation(now - timedelta(minutes=15), Decimal("0.10")),
        PriceObservation(datetime(2026, 9, 18, 11), Decimal("0.20")),
    )

    trends = calculate_price_trends(observations, now=now)

    assert trends.moving_average_1h is None
    assert trends.mean_24h is None
    assert trends.coverage_1h == timedelta(minutes=30)
    assert trends.coverage_24h == timedelta(minutes=30)


def test_old_observation_does_not_fill_missing_price_history() -> None:
    """A lone price sample cannot be carried across a missing day of history."""

    now = datetime(2026, 9, 18, 12, tzinfo=UTC)
    observations = (PriceObservation(now - timedelta(hours=23), Decimal("0.20")),)

    trends = calculate_price_trends(observations, now=now)

    assert trends.moving_average_1h is None
    assert trends.mean_24h is None
    assert trends.coverage_1h == timedelta(0)
    assert trends.coverage_24h == timedelta(minutes=20)
