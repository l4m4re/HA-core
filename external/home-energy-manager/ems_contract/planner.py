"""Deterministic, read-only quarter-hour EMS shadow planning."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from math import ceil
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .growatt import PriorityMode, XhScheduleSlot
from .providers import PriceInterval, PriceProviderState
from .snapshot import EmsSnapshot, GrowattState

QUARTER_HOUR = timedelta(minutes=15)
_SCHEDULE_START_REGISTERS = (3038, 3040, 3042, 3044, 3050, 3052, 3054, 3056, 3058)


class ShadowMode(StrEnum):
    """Economic mode requested from the pure planner."""

    SELF_CONSUMPTION = "self_consumption"
    CHEAP_CHARGE = "cheap_charge"
    FAILSAFE = "failsafe"
    PROFIT_EXPORT = "profit_export"


class PlannerReason(StrEnum):
    """Stable machine-readable explanations for plan decisions."""

    LOWEST_AVAILABLE_PRICE = "lowest_available_price"
    REQUIRED_TO_REACH_TARGET_SOC = "required_to_reach_target_soc"
    MERGED_FOR_SCHEDULE_SLOT_LIMIT = "merged_for_schedule_slot_limit"
    SKIPPED_CAPACITY_ALREADY_SATISFIED = "skipped_capacity_already_satisfied"
    SKIPPED_PRICE_TOO_HIGH = "skipped_price_too_high"
    FAILSAFE_STALE_TELEMETRY = "failsafe_stale_telemetry"
    FAILSAFE_INVALID_PRICE_DATA = "failsafe_invalid_price_data"
    FAILSAFE_STALE_PRICE_DATA = "failsafe_stale_price_data"
    FAILSAFE_PRICE_HORIZON = "failsafe_price_horizon"
    FAILSAFE_TIMEZONE = "failsafe_timezone"
    FAILSAFE_SOC_INVALID = "failsafe_soc_invalid"
    EXPORT_PRICE_UNAVAILABLE = "export_price_unavailable"
    TARGET_SOC_ALREADY_REACHED = "target_soc_already_reached"
    TARGET_SOC_UNMET = "target_soc_unmet"
    NO_CHANGE = "no_change"


@dataclass(frozen=True)
class PlannerConfig:
    """Explicit household and freshness assumptions for shadow planning."""

    timezone: str = "Europe/Amsterdam"
    battery_usable_capacity_kwh: Decimal = Decimal(10)
    reserve_soc_pct: Decimal = Decimal(10)
    normal_upper_soc_pct: Decimal = Decimal(70)
    cheap_charge_upper_soc_pct: Decimal = Decimal(80)
    maximum_ac_battery_charge_power_w: Decimal = Decimal(3000)
    charging_efficiency: Decimal = Decimal("0.92")
    battery_wear_cost_eur_per_kwh_stored: Decimal = Decimal("0.05")
    battery_wear_assumption: str = "provisional_example_not_device_specific"
    minimum_telemetry_freshness: timedelta = timedelta(minutes=5)
    minimum_price_data_freshness: timedelta = timedelta(minutes=20)
    required_forecast_horizon: timedelta = timedelta(hours=8)
    grid_service_current_limit_a: Decimal = Decimal(35)
    grid_safety_margin_a: Decimal = Decimal(3)
    maximum_growatt_schedule_slots: int = 9
    maximum_acceptable_import_price: Decimal | None = None

    def __post_init__(self) -> None:
        """Reject assumptions that would make a shadow plan unsafe."""
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone_invalid") from exc
        if not self.battery_usable_capacity_kwh > 0:
            raise ValueError("battery_capacity_invalid")
        if not 0 < self.charging_efficiency <= 1:
            raise ValueError("charging_efficiency_invalid")
        if self.battery_wear_cost_eur_per_kwh_stored < 0:
            raise ValueError("battery_wear_cost_invalid")
        if not self.maximum_ac_battery_charge_power_w > 0:
            raise ValueError("charge_power_invalid")
        if not 0 < self.maximum_growatt_schedule_slots <= 9:
            raise ValueError("schedule_slot_limit_invalid")
        if not 0 <= self.reserve_soc_pct <= self.normal_upper_soc_pct <= 100:
            raise ValueError("normal_soc_limits_invalid")
        if not self.normal_upper_soc_pct <= self.cheap_charge_upper_soc_pct <= 100:
            raise ValueError("cheap_soc_limits_invalid")

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> PlannerConfig:
        """Build configuration from a JSON-friendly mapping."""

        values = dict(data)
        decimal_fields = {
            "battery_usable_capacity_kwh",
            "reserve_soc_pct",
            "normal_upper_soc_pct",
            "cheap_charge_upper_soc_pct",
            "maximum_ac_battery_charge_power_w",
            "charging_efficiency",
            "battery_wear_cost_eur_per_kwh_stored",
            "grid_service_current_limit_a",
            "grid_safety_margin_a",
            "maximum_acceptable_import_price",
        }
        for field in decimal_fields:
            if field in values and values[field] is not None:
                values[field] = Decimal(str(values[field]))
        duration_fields = {
            "minimum_telemetry_freshness": "minimum_telemetry_freshness_minutes",
            "minimum_price_data_freshness": "minimum_price_data_freshness_minutes",
            "required_forecast_horizon": "required_forecast_horizon_hours",
        }
        for field, source in duration_fields.items():
            if source in values:
                amount = values.pop(source)
                values[field] = timedelta(
                    minutes=float(amount) * (60 if source.endswith("hours") else 1)
                )
        return cls(**values)


@dataclass(frozen=True)
class ScheduleWindow:
    """A conservative, representable logical Battery First window."""

    start: datetime
    end: datetime
    reason_codes: tuple[str, ...] = ()
    approximate: bool = False


@dataclass(frozen=True)
class ScheduleSlotIntent:
    """Packed words the future executor could compare, never write here."""

    slot: int
    start: datetime | None
    end: datetime | None
    enabled: bool
    priority: PriorityMode | None
    raw_start_word: int
    raw_end_word: int


@dataclass(frozen=True)
class ScheduleDiff:
    """Actual-versus-desired slot comparison."""

    slot: int
    actual_start_word: int | None
    actual_end_word: int | None
    desired_start_word: int
    desired_end_word: int
    changed: bool


@dataclass(frozen=True)
class WriteBudgetItem:
    """Shadow write accounting for one persistent schedule slot."""

    control: str
    registers: tuple[str, str]
    old_raw: tuple[int | None, int | None]
    desired_raw: tuple[int, int]
    changed: bool
    would_skip_no_change: bool
    reason: str


@dataclass(frozen=True)
class GridObservation:
    """Independent P1/grid-point values for a non-controlling diagnostic."""

    import_power_w: float | None
    export_power_w: float | None
    observed_at: datetime | None


@dataclass(frozen=True)
class CrossSourceDiagnostic:
    """Approximate power balance; never an electrical protection decision."""

    residual_w: float | None
    observation_age_mismatch_seconds: float | None
    informative: bool
    reason: str


@dataclass(frozen=True)
class BatteryChargeEconomics:
    """Cost and conversion-loss estimate for the scheduled charge windows."""

    grid_energy_kwh: Decimal
    stored_energy_kwh: Decimal
    conversion_loss_kwh: Decimal
    import_cost_eur: Decimal
    wear_cost_eur: Decimal
    total_charge_cost_eur: Decimal
    cost_per_stored_kwh_eur: Decimal | None
    wear_cost_eur_per_kwh_stored: Decimal
    wear_assumption: str


@dataclass(frozen=True)
class ShadowPlan:
    """Structured, explainable shadow output with no actuator handle."""

    generated_at: datetime
    valid: bool
    mode: ShadowMode
    reason_codes: tuple[str, ...]
    current_soc: Decimal | None
    reserve_soc: Decimal
    target_soc: Decimal | None
    required_energy_kwh: Decimal
    estimated_grid_energy_kwh: Decimal
    estimated_charging_duration_hours: Decimal
    compression_extra_cost_eur: Decimal
    compression_added_interval_count: int
    price_intervals_considered: tuple[PriceInterval, ...]
    selected_cheap_intervals: tuple[PriceInterval, ...]
    economic_windows: tuple[ScheduleWindow, ...]
    growatt_candidate_windows: tuple[ScheduleWindow, ...]
    actual_current_priority: object | None
    actual_schedule: tuple[XhScheduleSlot, ...]
    desired_logical_schedule: tuple[ScheduleWindow, ...]
    desired_slots: tuple[ScheduleSlotIntent, ...]
    schedule_diff: tuple[ScheduleDiff, ...]
    write_budget: tuple[WriteBudgetItem, ...]
    hypothetical_write_count: int
    skipped_no_change_count: int
    boundary_semantics_unvalidated: bool
    export_optimization_enabled: bool
    warnings: tuple[str, ...]
    invalid_reasons: tuple[str, ...]
    diagnostics: tuple[str, ...]
    cross_source: CrossSourceDiagnostic | None = None
    battery_economics: BatteryChargeEconomics | None = None

    def as_dict(self) -> dict[str, object]:
        """Return compact JSON-friendly output for the CLI and HA diagnostics."""

        return {
            "generated_at": self.generated_at.isoformat(),
            "valid": self.valid,
            "mode": self.mode.value,
            "reason_codes": list(self.reason_codes),
            "current_soc": _decimal(self.current_soc),
            "reserve_soc": _decimal(self.reserve_soc),
            "target_soc": _decimal(self.target_soc),
            "required_energy_kwh": _decimal(self.required_energy_kwh),
            "estimated_grid_energy_kwh": _decimal(self.estimated_grid_energy_kwh),
            "estimated_charging_duration_hours": _decimal(
                self.estimated_charging_duration_hours
            ),
            "compression_extra_cost_eur": _decimal(self.compression_extra_cost_eur),
            "compression_added_interval_count": self.compression_added_interval_count,
            "price_intervals_considered": [
                _interval(item) for item in self.price_intervals_considered
            ],
            "selected_cheap_intervals": [
                _interval(item) for item in self.selected_cheap_intervals
            ],
            "economic_windows": [_window(item) for item in self.economic_windows],
            "growatt_candidate_windows": [
                _window(item) for item in self.growatt_candidate_windows
            ],
            "actual_current_priority": getattr(
                self.actual_current_priority, "as_dict", lambda: None
            )(),
            "actual_schedule": [item.as_dict() for item in self.actual_schedule],
            "desired_logical_schedule": [
                _window(item) for item in self.desired_logical_schedule
            ],
            "desired_slots": [_slot(item) for item in self.desired_slots],
            "schedule_diff": [_diff(item) for item in self.schedule_diff],
            "write_budget": [_write(item) for item in self.write_budget],
            "hypothetical_write_count": self.hypothetical_write_count,
            "skipped_no_change_count": self.skipped_no_change_count,
            "boundary_semantics_unvalidated": self.boundary_semantics_unvalidated,
            "export_optimization_enabled": self.export_optimization_enabled,
            "warnings": list(self.warnings),
            "invalid_reasons": list(self.invalid_reasons),
            "diagnostics": list(self.diagnostics),
            "cross_source": _cross_source(self.cross_source),
            "battery_economics": (
                {
                    "grid_energy_kwh": _decimal(self.battery_economics.grid_energy_kwh),
                    "stored_energy_kwh": _decimal(
                        self.battery_economics.stored_energy_kwh
                    ),
                    "conversion_loss_kwh": _decimal(
                        self.battery_economics.conversion_loss_kwh
                    ),
                    "import_cost_eur": _decimal(self.battery_economics.import_cost_eur),
                    "wear_cost_eur": _decimal(self.battery_economics.wear_cost_eur),
                    "total_charge_cost_eur": _decimal(
                        self.battery_economics.total_charge_cost_eur
                    ),
                    "cost_per_stored_kwh_eur": _decimal(
                        self.battery_economics.cost_per_stored_kwh_eur
                    ),
                    "wear_cost_eur_per_kwh_stored": _decimal(
                        self.battery_economics.wear_cost_eur_per_kwh_stored
                    ),
                    "wear_assumption": self.battery_economics.wear_assumption,
                }
                if self.battery_economics is not None
                else None
            ),
        }


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _interval(item: PriceInterval) -> dict[str, object]:
    return {
        "start": item.start.isoformat(),
        "end": item.end.isoformat(),
        "import_price": _decimal(item.import_price),
        "export_price": _decimal(item.export_price),
        "source": item.source,
        "price_basis": item.price_basis.value,
        "tax_excluded_price": _decimal(item.tax_excluded_price),
    }


def _window(item: ScheduleWindow) -> dict[str, object]:
    return {
        "start": item.start.isoformat(),
        "end": item.end.isoformat(),
        "reason_codes": list(item.reason_codes),
        "approximate": item.approximate,
    }


def _slot(item: ScheduleSlotIntent) -> dict[str, object]:
    return {
        "slot": item.slot,
        "start": item.start.isoformat() if item.start else None,
        "end": item.end.isoformat() if item.end else None,
        "enabled": item.enabled,
        "priority": item.priority.name.lower() if item.priority else None,
        "raw_start_word": item.raw_start_word,
        "raw_end_word": item.raw_end_word,
    }


def _diff(item: ScheduleDiff) -> dict[str, object]:
    return {
        "slot": item.slot,
        "actual_start_word": item.actual_start_word,
        "actual_end_word": item.actual_end_word,
        "desired_start_word": item.desired_start_word,
        "desired_end_word": item.desired_end_word,
        "changed": item.changed,
    }


def _write(item: WriteBudgetItem) -> dict[str, object]:
    return {
        "control": item.control,
        "registers": list(item.registers),
        "old_raw": list(item.old_raw),
        "desired_raw": list(item.desired_raw),
        "changed": item.changed,
        "would_skip_no_change": item.would_skip_no_change,
        "reason": item.reason,
    }


def _cross_source(item: CrossSourceDiagnostic | None) -> dict[str, object] | None:
    if item is None:
        return None
    return {
        "residual_w": item.residual_w,
        "observation_age_mismatch_seconds": item.observation_age_mismatch_seconds,
        "informative": item.informative,
        "reason": item.reason,
    }


def _unique_reasons(reasons: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(reasons))


def _age_seconds(now: datetime, observed: datetime | None) -> float | None:
    if observed is None or observed.tzinfo is None or observed.utcoffset() is None:
        return None
    return (now - observed).total_seconds()


def _validate_intervals(
    current: PriceInterval | None,
    future: Sequence[PriceInterval],
) -> str | None:
    intervals = list(([current] if current else []) + list(future))
    ordered = sorted(intervals, key=lambda item: item.start)
    for index, item in enumerate(ordered):
        if item.start.tzinfo is None or item.end.tzinfo is None:
            return "timezone_naive_price_interval"
        if item.end <= item.start or item.end - item.start != QUARTER_HOUR:
            return "malformed_price_interval"
        if index and item.start != ordered[index - 1].end:
            return "price_intervals_overlap_or_gap"
    return None


def _window_groups(intervals: Sequence[PriceInterval]) -> list[ScheduleWindow]:
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda item: item.start)
    groups: list[ScheduleWindow] = []
    start = ordered[0].start
    end = ordered[0].end
    reasons = {PlannerReason.LOWEST_AVAILABLE_PRICE.value}
    for interval in ordered[1:]:
        if interval.start != end:
            groups.append(ScheduleWindow(start, end, tuple(sorted(reasons))))
            start = interval.start
            reasons = {PlannerReason.LOWEST_AVAILABLE_PRICE.value}
        end = interval.end
    groups.append(ScheduleWindow(start, end, tuple(sorted(reasons))))
    return groups


def _split_midnight(
    windows: Sequence[ScheduleWindow], timezone: ZoneInfo
) -> list[ScheduleWindow]:
    result: list[ScheduleWindow] = []
    for window in windows:
        start = window.start
        while (
            start.astimezone(timezone).date() < window.end.astimezone(timezone).date()
        ):
            next_date = start.astimezone(timezone).date() + timedelta(days=1)
            midnight = datetime.combine(next_date, datetime.min.time(), tzinfo=timezone)
            result.append(
                ScheduleWindow(start, midnight, window.reason_codes, window.approximate)
            )
            start = midnight
        result.append(
            ScheduleWindow(start, window.end, window.reason_codes, window.approximate)
        )
    return result


def _compress_windows(
    windows: Sequence[ScheduleWindow],
    intervals: Sequence[PriceInterval],
    maximum: int,
    power_kwh: Decimal,
) -> list[ScheduleWindow]:
    result = list(windows)
    all_intervals = sorted(intervals, key=lambda item: item.start)
    while len(result) > maximum:
        candidates: list[tuple[Decimal, timedelta, int]] = []
        for index in range(len(result) - 1):
            left, right = result[index], result[index + 1]
            bridge = [
                item
                for item in all_intervals
                if item.start >= left.end and item.end <= right.start
            ]
            penalty = sum(
                (item.import_price or Decimal(0)) * power_kwh for item in bridge
            )
            candidates.append((penalty, right.start - left.end, index))
        _, _, index = min(candidates, key=lambda item: (item[0], item[1], item[2]))
        left, right = result[index], result[index + 1]
        result[index : index + 2] = [
            ScheduleWindow(
                left.start,
                right.end,
                _unique_reasons(
                    (
                        *left.reason_codes,
                        *right.reason_codes,
                        PlannerReason.MERGED_FOR_SCHEDULE_SLOT_LIMIT.value,
                    )
                ),
                True,
            )
        ]
    return result


def _pack_time(value: datetime | None) -> int:
    if value is None:
        return 0
    local = value
    return (local.hour << 8) | local.minute


def _desired_slots(
    windows: Sequence[ScheduleWindow], maximum: int
) -> tuple[ScheduleSlotIntent, ...]:
    slots: list[ScheduleSlotIntent] = []
    for slot in range(1, maximum + 1):
        window = windows[slot - 1] if slot <= len(windows) else None
        if window is None:
            slots.append(ScheduleSlotIntent(slot, None, None, False, None, 0, 0))
            continue
        slots.append(
            ScheduleSlotIntent(
                slot,
                window.start,
                window.end,
                True,
                PriorityMode.BATTERY_FIRST,
                _pack_time(window.start) | 0x8000 | (PriorityMode.BATTERY_FIRST << 13),
                _pack_time(window.end),
            )
        )
    return tuple(slots)


def _diff_and_budget(
    actual: Sequence[XhScheduleSlot],
    desired: Sequence[ScheduleSlotIntent],
) -> tuple[tuple[ScheduleDiff, ...], tuple[WriteBudgetItem, ...]]:
    actual_by_slot = {item.slot: item for item in actual}
    diffs: list[ScheduleDiff] = []
    budget: list[WriteBudgetItem] = []
    for item in desired:
        current = actual_by_slot.get(item.slot)
        old = (
            (current.raw_start_word, current.raw_end_word)
            if current is not None
            else (None, None)
        )
        changed = old != (item.raw_start_word, item.raw_end_word)
        diffs.append(
            ScheduleDiff(
                item.slot,
                old[0],
                old[1],
                item.raw_start_word,
                item.raw_end_word,
                changed,
            )
        )
        budget.append(
            WriteBudgetItem(
                f"xh_schedule_slot_{item.slot}",
                (
                    f"H{_SCHEDULE_START_REGISTERS[item.slot - 1]}",
                    f"H{_SCHEDULE_START_REGISTERS[item.slot - 1] + 1}",
                ),
                old,
                (item.raw_start_word, item.raw_end_word),
                changed,
                not changed,
                "DESIRED_SHADOW_DIFF" if changed else PlannerReason.NO_CHANGE.value,
            )
        )
    return tuple(diffs), tuple(budget)


def _charge_economics(
    intervals: Sequence[PriceInterval], config: PlannerConfig
) -> BatteryChargeEconomics | None:
    """Estimate scheduled grid energy, conversion losses, and wear cost."""

    if any(item.import_price is None for item in intervals):
        return None
    grid_per_interval = (
        config.maximum_ac_battery_charge_power_w * Decimal("0.25") / Decimal(1000)
    )
    grid_energy = grid_per_interval * len(intervals)
    stored_energy = grid_energy * config.charging_efficiency
    conversion_loss = grid_energy - stored_energy
    import_cost = sum(
        (item.import_price or Decimal(0)) * grid_per_interval for item in intervals
    )
    wear_cost = stored_energy * config.battery_wear_cost_eur_per_kwh_stored
    total_cost = import_cost + wear_cost
    cost_per_stored_kwh = total_cost / stored_energy if stored_energy > 0 else None
    return BatteryChargeEconomics(
        grid_energy_kwh=grid_energy,
        stored_energy_kwh=stored_energy,
        conversion_loss_kwh=conversion_loss,
        import_cost_eur=import_cost,
        wear_cost_eur=wear_cost,
        total_charge_cost_eur=total_cost,
        cost_per_stored_kwh_eur=cost_per_stored_kwh,
        wear_cost_eur_per_kwh_stored=(config.battery_wear_cost_eur_per_kwh_stored),
        wear_assumption=config.battery_wear_assumption,
    )


def cross_source_balance(
    growatt: GrowattState,
    grid: GridObservation,
    *,
    max_age_mismatch: timedelta = timedelta(minutes=2),
) -> CrossSourceDiagnostic:
    """Calculate a tolerant PV/battery/grid/load residual for diagnostics."""

    values = (
        growatt.pv_power_w,
        growatt.house_load_power_w,
        grid.import_power_w,
        grid.export_power_w,
        growatt.observed_at,
        grid.observed_at,
    )
    if any(value is None for value in values):
        return CrossSourceDiagnostic(None, None, False, "required_value_missing")
    assert growatt.observed_at is not None
    assert grid.observed_at is not None
    age_mismatch = abs((growatt.observed_at - grid.observed_at).total_seconds())
    if age_mismatch > max_age_mismatch.total_seconds():
        return CrossSourceDiagnostic(
            None, age_mismatch, False, "observation_age_mismatch"
        )
    charge = 0.0
    discharge = growatt.battery_power_w or 0.0
    residual = (
        growatt.pv_power_w
        + discharge
        + grid.import_power_w
        - grid.export_power_w
        - growatt.house_load_power_w
        - charge
    )
    return CrossSourceDiagnostic(residual, age_mismatch, True, "informative_only")


def _failsafe_plan(
    snapshot: EmsSnapshot,
    config: PlannerConfig,
    reasons: Sequence[str],
    warnings: Sequence[str] = (),
    cross_source: CrossSourceDiagnostic | None = None,
) -> ShadowPlan:
    desired = _desired_slots((), config.maximum_growatt_schedule_slots)
    diffs, budget = _diff_and_budget(snapshot.growatt.schedule, desired)
    return ShadowPlan(
        generated_at=snapshot.timestamp,
        valid=False,
        mode=ShadowMode.FAILSAFE,
        reason_codes=_unique_reasons(reasons),
        current_soc=(
            Decimal(str(snapshot.growatt.battery_soc_pct))
            if snapshot.growatt.battery_soc_pct is not None
            else None
        ),
        reserve_soc=config.reserve_soc_pct,
        target_soc=None,
        required_energy_kwh=Decimal(0),
        estimated_grid_energy_kwh=Decimal(0),
        estimated_charging_duration_hours=Decimal(0),
        compression_extra_cost_eur=Decimal(0),
        compression_added_interval_count=0,
        price_intervals_considered=(),
        selected_cheap_intervals=(),
        economic_windows=(),
        growatt_candidate_windows=(),
        actual_current_priority=snapshot.growatt.current_priority,
        actual_schedule=snapshot.growatt.schedule,
        desired_logical_schedule=(),
        desired_slots=desired,
        schedule_diff=diffs,
        write_budget=budget,
        hypothetical_write_count=sum(item.changed for item in budget),
        skipped_no_change_count=sum(item.would_skip_no_change for item in budget),
        boundary_semantics_unvalidated=True,
        export_optimization_enabled=False,
        warnings=tuple(warnings),
        invalid_reasons=_unique_reasons(reasons),
        diagnostics=("FAILSAFE: prefer normal self-consumption; no economic action",),
        cross_source=cross_source,
    )


def plan_shadow_ems(
    snapshot: EmsSnapshot,
    config: PlannerConfig,
    *,
    requested_mode: ShadowMode = ShadowMode.CHEAP_CHARGE,
    price: PriceProviderState | None = None,
    grid: GridObservation | None = None,
) -> ShadowPlan:
    """Calculate a deterministic shadow plan without any I/O or actuator."""

    price = price or snapshot.price
    cross_source = (
        cross_source_balance(snapshot.growatt, grid) if grid is not None else None
    )
    try:
        ZoneInfo(config.timezone)
    except ZoneInfoNotFoundError:
        return _failsafe_plan(
            snapshot,
            config,
            (PlannerReason.FAILSAFE_TIMEZONE.value,),
            cross_source=cross_source,
        )
    if not snapshot.timestamp.tzinfo or snapshot.timestamp.utcoffset() is None:
        return _failsafe_plan(
            snapshot,
            config,
            (PlannerReason.FAILSAFE_TIMEZONE.value,),
            cross_source=cross_source,
        )
    g = snapshot.growatt
    age = _age_seconds(snapshot.timestamp, g.observed_at)
    if (
        not g.telemetry_valid
        or age is None
        or age < 0
        or age > config.minimum_telemetry_freshness.total_seconds()
    ):
        return _failsafe_plan(
            snapshot,
            config,
            (PlannerReason.FAILSAFE_STALE_TELEMETRY.value,),
            cross_source=cross_source,
        )
    if g.battery_soc_pct is None or not 0 <= g.battery_soc_pct <= 100:
        return _failsafe_plan(
            snapshot,
            config,
            (PlannerReason.FAILSAFE_SOC_INVALID.value,),
            cross_source=cross_source,
        )
    if requested_mode is ShadowMode.PROFIT_EXPORT:
        return _failsafe_plan(
            snapshot,
            config,
            (PlannerReason.EXPORT_PRICE_UNAVAILABLE.value,),
            cross_source=cross_source,
        )
    if price is None or not price.valid:
        return _failsafe_plan(
            snapshot,
            config,
            (PlannerReason.FAILSAFE_INVALID_PRICE_DATA.value,),
            cross_source=cross_source,
        )
    price_age = _age_seconds(snapshot.timestamp, price.retrieved_at)
    if (
        price_age is None
        or price_age < 0
        or price_age > config.minimum_price_data_freshness.total_seconds()
    ):
        return _failsafe_plan(
            snapshot,
            config,
            (PlannerReason.FAILSAFE_STALE_PRICE_DATA.value,),
            cross_source=cross_source,
        )
    interval_error = _validate_intervals(price.current, price.future)
    if interval_error:
        return _failsafe_plan(
            snapshot,
            config,
            (PlannerReason.FAILSAFE_INVALID_PRICE_DATA.value,),
            warnings=(interval_error,),
            cross_source=cross_source,
        )

    target = (
        config.cheap_charge_upper_soc_pct
        if requested_mode is ShadowMode.CHEAP_CHARGE
        else config.normal_upper_soc_pct
    )
    current_soc = Decimal(str(g.battery_soc_pct))
    required_battery = max(
        Decimal(0),
        config.battery_usable_capacity_kwh * (target - current_soc) / Decimal(100),
    )
    required_grid = required_battery / config.charging_efficiency
    duration = required_grid / (
        config.maximum_ac_battery_charge_power_w / Decimal(1000)
    )
    all_future = tuple(sorted(price.future, key=lambda item: item.start))
    interval_grid_kwh = (
        config.maximum_ac_battery_charge_power_w / Decimal(1000) * Decimal("0.25")
    )
    if requested_mode is ShadowMode.SELF_CONSUMPTION or required_battery == 0:
        selected: tuple[PriceInterval, ...] = ()
        economic: list[ScheduleWindow] = []
        candidates: list[ScheduleWindow] = []
    else:
        horizon_end = snapshot.timestamp + config.required_forecast_horizon
        if not all_future or all_future[-1].end < horizon_end:
            return _failsafe_plan(
                snapshot,
                config,
                (PlannerReason.FAILSAFE_PRICE_HORIZON.value,),
                warnings=("forecast_does_not_cover_required_horizon",),
                cross_source=cross_source,
            )
        needed_count = max(1, ceil(required_grid / interval_grid_kwh))
        ranked = sorted(
            (item for item in all_future if item.import_price is not None),
            key=lambda item: (item.import_price, item.start),
        )
        allowed = ranked
        if config.maximum_acceptable_import_price is not None:
            below = [
                item
                for item in ranked
                if item.import_price <= config.maximum_acceptable_import_price
            ]
            allowed = below or ranked
        selected_list = allowed[:needed_count]
        selected = tuple(sorted(selected_list, key=lambda item: item.start))
        if len(selected) < needed_count:
            return _failsafe_plan(
                snapshot,
                config,
                (PlannerReason.TARGET_SOC_UNMET.value,),
                warnings=("forecast_energy_capacity_insufficient",),
                cross_source=cross_source,
            )
        economic = _split_midnight(_window_groups(selected), ZoneInfo(config.timezone))
        candidates = _compress_windows(
            economic,
            all_future,
            config.maximum_growatt_schedule_slots,
            interval_grid_kwh,
        )
        if len(candidates) > config.maximum_growatt_schedule_slots:
            return _failsafe_plan(
                snapshot,
                config,
                (PlannerReason.TARGET_SOC_UNMET.value,),
                warnings=("schedule_slot_limit_unrepresentable",),
                cross_source=cross_source,
            )
        if len(candidates) < len(economic):
            candidates = [
                ScheduleWindow(
                    item.start,
                    item.end,
                    _unique_reasons(
                        (
                            *item.reason_codes,
                            PlannerReason.MERGED_FOR_SCHEDULE_SLOT_LIMIT.value,
                        )
                    ),
                    True,
                )
                for item in candidates
            ]
    desired = _desired_slots(candidates, config.maximum_growatt_schedule_slots)
    diffs, budget = _diff_and_budget(g.schedule, desired)
    candidate_intervals = tuple(
        item
        for item in all_future
        if any(
            window.start <= item.start and item.end <= window.end
            for window in candidates
        )
    )
    selected_set = set(selected)
    added_intervals = tuple(
        item for item in candidate_intervals if item not in selected_set
    )
    compression_cost = sum(
        (item.import_price or Decimal(0)) * interval_grid_kwh
        for item in added_intervals
    )
    warnings: list[str] = []
    battery_economics = _charge_economics(candidate_intervals, config)
    if battery_economics is None:
        warnings.append("candidate_price_missing_cost_estimate_unavailable")
    elif "provisional" in config.battery_wear_assumption.lower():
        warnings.append("battery_wear_cost_is_provisional")
    if any(item.approximate for item in candidates):
        warnings.append("schedule_windows_are_approximated_for_slot_limit")
    if requested_mode is ShadowMode.CHEAP_CHARGE and required_battery == 0:
        reason_codes = (PlannerReason.TARGET_SOC_ALREADY_REACHED.value,)
    else:
        reason_codes = (PlannerReason.LOWEST_AVAILABLE_PRICE.value,)
    return ShadowPlan(
        generated_at=snapshot.timestamp,
        valid=True,
        mode=(
            ShadowMode.SELF_CONSUMPTION
            if requested_mode is ShadowMode.SELF_CONSUMPTION
            else ShadowMode.CHEAP_CHARGE
        ),
        reason_codes=reason_codes,
        current_soc=current_soc,
        reserve_soc=config.reserve_soc_pct,
        target_soc=target,
        required_energy_kwh=required_battery,
        estimated_grid_energy_kwh=required_grid,
        estimated_charging_duration_hours=duration,
        compression_extra_cost_eur=compression_cost,
        compression_added_interval_count=len(added_intervals),
        price_intervals_considered=all_future,
        selected_cheap_intervals=selected,
        economic_windows=tuple(economic),
        growatt_candidate_windows=tuple(candidates),
        actual_current_priority=g.current_priority,
        actual_schedule=g.schedule,
        desired_logical_schedule=tuple(candidates),
        desired_slots=desired,
        schedule_diff=diffs,
        write_budget=budget,
        hypothetical_write_count=sum(item.changed for item in budget),
        skipped_no_change_count=sum(item.would_skip_no_change for item in budget),
        boundary_semantics_unvalidated=True,
        export_optimization_enabled=False,
        warnings=tuple(warnings),
        invalid_reasons=(),
        diagnostics=(
            "OUTSIDE_WINDOW_LOAD_FIRST=LIVE_OBSERVED; NOT_VENDOR_UNIVERSAL_RULE",
            "No Growatt/Peblar/Zoe actuator is connected to this plan.",
        ),
        cross_source=cross_source,
        battery_economics=battery_economics,
    )
