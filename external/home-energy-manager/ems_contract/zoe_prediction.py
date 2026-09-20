"""Empirical, read-only Zoe charging-rate model and projection."""

from collections.abc import Iterable, Mapping
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from pathlib import Path
from statistics import median

from .providers import PriceInterval, PriceProviderState

CURRENT_SETTINGS_A = (6, 8, 10, 13, 16)
SOC_BANDS = (
    ("low", 15.0, 40.0),
    ("middle", 40.0, 70.0),
    ("high", 70.0, 95.0),
)
_ALL_SOC = ("all", 0.0, 100.0)
REPLAY_TRAINING_DATA = Path(__file__).parent / "data/zoe/charge_replay_training.csv"


@dataclass(frozen=True)
class ZoeChargeSample:
    """One read-only poll sample used to fit or replay a charge session."""

    timestamp: datetime
    charging: bool
    soc_pct: float | None
    current_a: float | None
    power_w: float | None


@dataclass(frozen=True)
class ZoeRateEstimate:
    """Observed SoC rate for a charger setting and SoC band."""

    current_setting_a: int
    band: str
    soc_min_pct: float
    soc_max_pct: float
    rate_pct_per_hour: float
    slow_rate_pct_per_hour: float
    fast_rate_pct_per_hour: float
    training_sessions: int
    training_hours: float
    mean_power_w: float | None
    confidence: str


@dataclass(frozen=True)
class ZoeChargeWindow:
    """A planned period when the EVSE is expected to charge the vehicle."""

    start: datetime
    end: datetime


@dataclass(frozen=True)
class ZoeChargeSchedule:
    """Cheapest price intervals before departure for the estimated charge."""

    valid: bool
    required_duration_hours: float | None
    selected_intervals: tuple[PriceInterval, ...]
    windows: tuple[ZoeChargeWindow, ...]
    estimated_import_cost_eur: float | None
    price_basis: str | None
    reason: str | None


@dataclass(frozen=True)
class ZoeProjectionPoint:
    """A central and uncertainty-bound SoC estimate at one time."""

    timestamp: datetime
    soc_pct: float
    slow_soc_pct: float
    fast_soc_pct: float


@dataclass(frozen=True)
class ZoeChargeProjection:
    """A forecast that contains no vehicle or charger control handle."""

    valid: bool
    initial_soc_pct: float
    target_soc_pct: float
    current_setting_a: int
    predicted_finish: datetime | None
    slow_finish: datetime | None
    fast_finish: datetime | None
    projected_grid_energy_kwh: float | None
    confidence: str
    warnings: tuple[str, ...]
    points: tuple[ZoeProjectionPoint, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready projection for HA diagnostics and dashboards."""

        return {
            "valid": self.valid,
            "initial_soc_pct": round(self.initial_soc_pct, 2),
            "target_soc_pct": round(self.target_soc_pct, 2),
            "current_setting_a": self.current_setting_a,
            "predicted_finish": (
                self.predicted_finish.isoformat() if self.predicted_finish else None
            ),
            "slow_finish": self.slow_finish.isoformat() if self.slow_finish else None,
            "fast_finish": self.fast_finish.isoformat() if self.fast_finish else None,
            "projected_grid_energy_kwh": (
                round(self.projected_grid_energy_kwh, 3)
                if self.projected_grid_energy_kwh is not None
                else None
            ),
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "points": [
                {
                    "timestamp": point.timestamp.isoformat(),
                    "soc_pct": round(point.soc_pct, 2),
                    "slow_soc_pct": round(point.slow_soc_pct, 2),
                    "fast_soc_pct": round(point.fast_soc_pct, 2),
                }
                for point in self.points
            ],
        }


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except TypeError, ValueError:
        return None
    return number if math.isfinite(number) else None


def _row_value(row: Mapping[str, str], *keys: str) -> float | None:
    for key in keys:
        value = _number(row.get(key))
        if value is not None:
            return value
    return None


def load_poller_csv(path: str | Path) -> tuple[ZoeChargeSample, ...]:
    """Load the small relevant subset of a PyCanZE poller CSV."""

    samples: list[ZoeChargeSample] = []
    with Path(path).open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            try:
                timestamp = datetime.fromisoformat(row.get("timestamp", ""))
            except ValueError:
                continue
            soc = _row_value(row, "soc_pct", "soc")
            if soc is not None and not 0 < soc <= 100:
                soc = None
            current = _row_value(row, "current_a", "shelly_current_a")
            power = _row_value(row, "power_w", "shelly_apower_w")
            voltage = _row_value(row, "shelly_voltage_v")
            if (
                current is None
                and power is not None
                and voltage is not None
                and voltage > 10
            ):
                current = power / voltage
            if current is None:
                current = _row_value(row, "chg_set_A")
            charging_value = (row.get("charging") or "").strip().lower()
            charging = (
                charging_value in {"true", "1", "yes"}
                if charging_value in {"true", "1", "yes", "false", "0", "no"}
                else (row.get("state") or "").strip().lower() == "charging"
            )
            samples.append(
                ZoeChargeSample(
                    timestamp=timestamp,
                    charging=charging,
                    soc_pct=soc,
                    current_a=current,
                    power_w=power,
                )
            )
    return tuple(sorted(samples, key=lambda sample: sample.timestamp))


def split_charge_sessions(
    samples: Iterable[ZoeChargeSample],
    *,
    maximum_gap: timedelta = timedelta(minutes=30),
) -> tuple[tuple[ZoeChargeSample, ...], ...]:
    """Split charging samples at unplugged polls and long collection gaps."""

    sessions: list[tuple[ZoeChargeSample, ...]] = []
    current: list[ZoeChargeSample] = []
    previous: datetime | None = None
    for sample in sorted(samples, key=lambda item: item.timestamp):
        if not sample.charging or (
            previous is not None and sample.timestamp - previous > maximum_gap
        ):
            if current:
                sessions.append(tuple(current))
            current = []
        if sample.charging:
            current.append(sample)
        previous = sample.timestamp
    if current:
        sessions.append(tuple(current))
    return tuple(sessions)


def _setting_for(samples: Iterable[ZoeChargeSample]) -> int | None:
    currents = [sample.current_a for sample in samples if sample.current_a is not None]
    if not currents:
        return None
    observed = median(currents)
    setting = min(CURRENT_SETTINGS_A, key=lambda item: abs(item - observed))
    if abs(setting - observed) > setting * 0.25:
        return None
    return setting


def _regression_rate(
    samples: list[ZoeChargeSample],
    *,
    minimum_duration: timedelta,
    minimum_soc_gain_pct: float,
) -> tuple[float, float, float] | None:
    points = [sample for sample in samples if sample.soc_pct is not None]
    if len(points) < 3:
        return None
    duration_hours = (points[-1].timestamp - points[0].timestamp).total_seconds() / 3600
    soc_gain = points[-1].soc_pct - points[0].soc_pct  # type: ignore[operator]
    if (
        duration_hours <= 0
        or duration_hours < minimum_duration.total_seconds() / 3600
        or soc_gain < minimum_soc_gain_pct
    ):
        return None
    elapsed_hours = [
        (sample.timestamp - points[0].timestamp).total_seconds() / 3600
        for sample in points
    ]
    soc_values = [sample.soc_pct for sample in points]
    mean_time = sum(elapsed_hours) / len(elapsed_hours)
    mean_soc = sum(soc_values) / len(soc_values)  # type: ignore[arg-type]
    denominator = sum((value - mean_time) ** 2 for value in elapsed_hours)
    if denominator <= 0:
        return None
    rate = (
        sum(
            (elapsed - mean_time) * (soc - mean_soc)
            for elapsed, soc in zip(elapsed_hours, soc_values, strict=True)
        )
        / denominator
    )
    if rate <= 0:
        return None
    return rate, duration_hours, soc_gain


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def fit_charge_rate_model(
    samples: Iterable[ZoeChargeSample],
    *,
    maximum_gap: timedelta = timedelta(minutes=30),
    minimum_duration: timedelta = timedelta(minutes=15),
    minimum_soc_gain_pct: float = 0.5,
) -> tuple[ZoeRateEstimate, ...]:
    """Fit per-session rates by measured current setting and SoC band."""

    observations: dict[tuple[int, str], list[tuple[float, float, float | None]]] = {}
    bands = (*SOC_BANDS, _ALL_SOC)
    for session in split_charge_sessions(samples, maximum_gap=maximum_gap):
        for band, low, high in bands:
            band_samples = [
                sample
                for sample in session
                if sample.soc_pct is not None and low <= sample.soc_pct < high
            ]
            setting = _setting_for(band_samples)
            if setting is None:
                continue
            regression = _regression_rate(
                band_samples,
                minimum_duration=minimum_duration,
                minimum_soc_gain_pct=minimum_soc_gain_pct,
            )
            if regression is None:
                continue
            rate, duration_hours, _ = regression
            powers = [sample.power_w for sample in band_samples if sample.power_w]
            observations.setdefault((setting, band), []).append(
                (
                    rate,
                    duration_hours,
                    median(powers) if powers else None,
                )
            )

    estimates: list[ZoeRateEstimate] = []
    for (setting, band), records in sorted(observations.items()):
        rates = [record[0] for record in records]
        hours = sum(record[1] for record in records)
        power_values = [record[2] for record in records if record[2] is not None]
        session_count = len(records)
        confidence = (
            "high"
            if session_count >= 8 and hours >= 20
            else "medium"
            if session_count >= 3 and hours >= 4
            else "low"
        )
        low, high = next(
            (low, high) for current_band, low, high in bands if current_band == band
        )
        estimates.append(
            ZoeRateEstimate(
                current_setting_a=setting,
                band=band,
                soc_min_pct=low,
                soc_max_pct=high,
                rate_pct_per_hour=median(rates),
                slow_rate_pct_per_hour=_percentile(rates, 0.1),
                fast_rate_pct_per_hour=_percentile(rates, 0.9),
                training_sessions=session_count,
                training_hours=hours,
                mean_power_w=median(power_values) if power_values else None,
                confidence=confidence,
            )
        )
    return tuple(estimates)


def load_replay_rate_model(
    path: str | Path = REPLAY_TRAINING_DATA,
) -> tuple[ZoeRateEstimate, ...]:
    """Load the checked-in sanitized training capture for DEV/demo use."""

    return fit_charge_rate_model(load_poller_csv(path))


def _lookup_rate(
    model: tuple[ZoeRateEstimate, ...], soc_pct: float, current_setting_a: int
) -> tuple[ZoeRateEstimate, bool] | None:
    exact = next(
        (
            estimate
            for estimate in model
            if estimate.current_setting_a == current_setting_a
            and estimate.band != "all"
            and estimate.soc_min_pct <= soc_pct < estimate.soc_max_pct
        ),
        None,
    )
    if exact is not None:
        return exact, False
    fallback = next(
        (
            estimate
            for estimate in model
            if estimate.current_setting_a == current_setting_a
            and estimate.band == "all"
        ),
        None,
    )
    if fallback is not None:
        return fallback, True
    nearest = [estimate for estimate in model if estimate.band == "all"]
    if nearest:
        estimate = min(
            nearest,
            key=lambda item: abs(item.current_setting_a - current_setting_a),
        )
        return estimate, True
    return None


def estimate_charge_duration_hours(
    model: tuple[ZoeRateEstimate, ...],
    *,
    initial_soc_pct: float,
    target_soc_pct: float,
    current_setting_a: int,
) -> float | None:
    """Integrate observed SoC rates across the required SoC bands."""

    if not 0 <= initial_soc_pct <= target_soc_pct <= 100:
        return None
    soc = initial_soc_pct
    hours = 0.0
    while soc < target_soc_pct:
        found = _lookup_rate(model, soc, current_setting_a)
        if found is None:
            return None
        estimate, _ = found
        boundary = min(
            (upper for _, lower, upper in SOC_BANDS if lower <= soc < upper),
            default=target_soc_pct,
        )
        next_soc = min(target_soc_pct, boundary)
        if next_soc <= soc:
            next_soc = target_soc_pct
        hours += (next_soc - soc) / estimate.rate_pct_per_hour
        soc = next_soc
    return hours


def plan_price_aware_charge(
    model: tuple[ZoeRateEstimate, ...],
    prices: PriceProviderState,
    *,
    now: datetime,
    earliest_start: datetime,
    departure: datetime,
    initial_soc_pct: float,
    target_soc_pct: float,
    current_setting_a: int,
) -> ZoeChargeSchedule:
    """Select the cheapest forecast intervals that fit before departure."""

    duration = estimate_charge_duration_hours(
        model,
        initial_soc_pct=initial_soc_pct,
        target_soc_pct=target_soc_pct,
        current_setting_a=current_setting_a,
    )
    if duration is None:
        return ZoeChargeSchedule(
            False, None, (), (), None, None, "charge_rate_unavailable"
        )
    if (
        not prices.valid
        or now.tzinfo is None
        or earliest_start.tzinfo is None
        or departure.tzinfo is None
        or departure <= max(now, earliest_start)
    ):
        return ZoeChargeSchedule(
            False, duration, (), (), None, None, "price_or_time_input_invalid"
        )
    intervals = tuple(
        sorted(
            (
                item
                for item in prices.future
                if item.valid
                and item.import_price is not None
                and item.start >= max(now, earliest_start)
                and item.end <= departure
            ),
            key=lambda item: (item.import_price, item.start),
        )
    )
    required_count = max(1, math.ceil(duration * 4))
    if len(intervals) < required_count:
        return ZoeChargeSchedule(
            False,
            duration,
            (),
            (),
            None,
            None,
            "price_forecast_too_short_before_departure",
        )
    selected = tuple(sorted(intervals[:required_count], key=lambda item: item.start))
    windows: list[ZoeChargeWindow] = []
    for interval in selected:
        if windows and windows[-1].end == interval.start:
            windows[-1] = ZoeChargeWindow(windows[-1].start, interval.end)
        else:
            windows.append(ZoeChargeWindow(interval.start, interval.end))
    power_estimates = [
        estimate.mean_power_w
        for estimate in model
        if estimate.current_setting_a == current_setting_a
        and estimate.mean_power_w is not None
    ]
    mean_power_w = median(power_estimates) if power_estimates else None
    estimated_cost = (
        sum(
            float(item.import_price)
            * mean_power_w
            * (item.end - item.start).total_seconds()
            / 3_600_000
            for item in selected
            if item.import_price is not None
        )
        if mean_power_w is not None
        else None
    )
    basis = (
        selected[0].price_basis.value
        if all(item.price_basis is selected[0].price_basis for item in selected)
        else "mixed"
    )
    return ZoeChargeSchedule(
        True,
        duration,
        selected,
        tuple(windows),
        estimated_cost,
        basis,
        None,
    )


def _simulate_projection(
    model: tuple[ZoeRateEstimate, ...],
    windows: tuple[ZoeChargeWindow, ...],
    *,
    initial_soc_pct: float,
    target_soc_pct: float,
    current_setting_a: int,
    rate_attribute: str,
) -> tuple[datetime | None, tuple[tuple[datetime, float], ...], float | None, bool]:
    soc = initial_soc_pct
    points: list[tuple[datetime, float]] = []
    power_energy_kwh = 0.0
    power_known = False
    used_fallback = False
    finish: datetime | None = None
    for window in windows:
        if window.start.tzinfo is None or window.end.tzinfo is None:
            return None, (), None, used_fallback
        if window.end <= window.start:
            return None, (), None, used_fallback
        cursor = window.start
        if not points or points[-1][0] < cursor:
            points.append((cursor, soc))
        while cursor < window.end and soc < target_soc_pct:
            found = _lookup_rate(model, soc, current_setting_a)
            if found is None:
                return None, tuple(points), None, used_fallback
            estimate, fallback = found
            used_fallback |= fallback
            rate = getattr(estimate, rate_attribute)
            step_hours = min(0.25, (window.end - cursor).total_seconds() / 3600)
            next_cursor = min(window.end, cursor + timedelta(hours=step_hours))
            elapsed_hours = (next_cursor - cursor).total_seconds() / 3600
            soc = min(target_soc_pct, soc + rate * elapsed_hours)
            points.append((next_cursor, soc))
            if estimate.mean_power_w is not None:
                power_energy_kwh += estimate.mean_power_w * elapsed_hours / 1000
                power_known = True
            cursor = next_cursor
            if soc >= target_soc_pct:
                finish = cursor
                break
        if finish is not None:
            break
    return (
        finish,
        tuple(points),
        power_energy_kwh if power_known else None,
        used_fallback,
    )


def project_charge_session(
    model: tuple[ZoeRateEstimate, ...],
    windows: Iterable[ZoeChargeWindow],
    *,
    initial_soc_pct: float,
    target_soc_pct: float,
    current_setting_a: int,
) -> ZoeChargeProjection:
    """Project SoC through charge windows, without operating an EVSE."""

    ordered_windows = tuple(sorted(windows, key=lambda window: window.start))
    if (
        not model
        or not ordered_windows
        or not 0 <= initial_soc_pct <= target_soc_pct <= 100
        or current_setting_a <= 0
    ):
        return ZoeChargeProjection(
            valid=False,
            initial_soc_pct=initial_soc_pct,
            target_soc_pct=target_soc_pct,
            current_setting_a=current_setting_a,
            predicted_finish=None,
            slow_finish=None,
            fast_finish=None,
            projected_grid_energy_kwh=None,
            confidence="unavailable",
            warnings=("invalid_projection_inputs",),
            points=(),
        )

    central_finish, central_points, energy, central_fallback = _simulate_projection(
        model,
        ordered_windows,
        initial_soc_pct=initial_soc_pct,
        target_soc_pct=target_soc_pct,
        current_setting_a=current_setting_a,
        rate_attribute="rate_pct_per_hour",
    )
    slow_finish, slow_points, _, slow_fallback = _simulate_projection(
        model,
        ordered_windows,
        initial_soc_pct=initial_soc_pct,
        target_soc_pct=target_soc_pct,
        current_setting_a=current_setting_a,
        rate_attribute="slow_rate_pct_per_hour",
    )
    fast_finish, fast_points, _, fast_fallback = _simulate_projection(
        model,
        ordered_windows,
        initial_soc_pct=initial_soc_pct,
        target_soc_pct=target_soc_pct,
        current_setting_a=current_setting_a,
        rate_attribute="fast_rate_pct_per_hour",
    )
    valid = bool(central_points)
    warnings: list[str] = []
    if central_fallback or slow_fallback or fast_fallback:
        warnings.append("rate_estimate_fallback_used")
    if central_finish is None:
        warnings.append("target_not_reached_in_charge_windows")
    if not any(
        estimate.confidence == "high"
        for estimate in model
        if estimate.current_setting_a == current_setting_a
    ):
        warnings.append("limited_training_sessions")
    confidence = (
        "high"
        if valid and not warnings and central_finish is not None
        else "medium"
        if valid and "limited_training_sessions" not in warnings
        else "low"
        if valid
        else "unavailable"
    )
    slow_by_time = dict(slow_points)
    fast_by_time = dict(fast_points)
    combined_points = tuple(
        ZoeProjectionPoint(
            timestamp=timestamp,
            soc_pct=soc,
            slow_soc_pct=slow_by_time.get(timestamp, soc),
            fast_soc_pct=fast_by_time.get(timestamp, soc),
        )
        for timestamp, soc in central_points
    )
    return ZoeChargeProjection(
        valid=valid,
        initial_soc_pct=initial_soc_pct,
        target_soc_pct=target_soc_pct,
        current_setting_a=current_setting_a,
        predicted_finish=central_finish,
        slow_finish=slow_finish,
        fast_finish=fast_finish,
        projected_grid_energy_kwh=energy,
        confidence=confidence,
        warnings=tuple(warnings),
        points=combined_points,
    )
