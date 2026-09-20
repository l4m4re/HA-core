"""Time-weighted trends over recorded dynamic-price observations."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

MAX_OBSERVATION_HOLD = timedelta(minutes=20)


@dataclass(frozen=True)
class PriceObservation:
    """One recorded all-in import tariff and the time it became effective."""

    timestamp: datetime
    price_eur_per_kwh: Decimal


@dataclass(frozen=True)
class PriceTrend:
    """Time-weighted rolling means with explicit history coverage."""

    moving_average_1h: Decimal | None
    mean_24h: Decimal | None
    coverage_1h: timedelta
    coverage_24h: timedelta
    observations_24h: int


def _time_weighted_average(
    observations: tuple[PriceObservation, ...],
    *,
    now: datetime,
    window: timedelta,
    minimum_coverage: float,
) -> tuple[Decimal | None, timedelta]:
    window_start = now - window
    weighted_sum = Decimal(0)
    coverage = timedelta(0)
    for index, observation in enumerate(observations):
        if observation.timestamp >= now:
            break
        next_time = (
            observations[index + 1].timestamp if index + 1 < len(observations) else now
        )
        interval_start = max(observation.timestamp, window_start)
        interval_end = min(
            next_time,
            observation.timestamp + MAX_OBSERVATION_HOLD,
            now,
        )
        if interval_end <= interval_start:
            continue
        duration = interval_end - interval_start
        weighted_sum += observation.price_eur_per_kwh * Decimal(
            str(duration.total_seconds())
        )
        coverage += duration
    if coverage.total_seconds() < window.total_seconds() * minimum_coverage:
        return None, coverage
    return weighted_sum / Decimal(str(coverage.total_seconds())), coverage


def calculate_price_trends(
    observations: Iterable[PriceObservation],
    *,
    now: datetime,
    minimum_coverage: float = 0.8,
) -> PriceTrend:
    """Calculate trailing one-hour and 24-hour all-in-price averages."""

    if now.tzinfo is None or now.utcoffset() is None:
        return PriceTrend(None, None, timedelta(0), timedelta(0), 0)
    valid = tuple(
        sorted(
            (
                item
                for item in observations
                if item.timestamp.tzinfo is not None
                and item.timestamp.utcoffset() is not None
            ),
            key=lambda item: item.timestamp,
        )
    )
    one_hour, coverage_1h = _time_weighted_average(
        valid,
        now=now,
        window=timedelta(hours=1),
        minimum_coverage=minimum_coverage,
    )
    daily_mean, coverage_24h = _time_weighted_average(
        valid,
        now=now,
        window=timedelta(hours=24),
        minimum_coverage=minimum_coverage,
    )
    count_24h = sum(now - timedelta(hours=24) <= item.timestamp < now for item in valid)
    return PriceTrend(
        moving_average_1h=one_hour,
        mean_24h=daily_mean,
        coverage_1h=coverage_1h,
        coverage_24h=coverage_24h,
        observations_24h=count_24h,
    )
