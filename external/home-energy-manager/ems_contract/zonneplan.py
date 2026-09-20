"""Pure adapter for the public Zonneplan ONE sensor shape."""

from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .providers import PriceBasis, PriceInterval, PriceProviderState

_AMOUNT_SCALE = Decimal(10000000)
_QUARTER_HOUR = timedelta(minutes=15)
_UNAVAILABLE_STATES = {"unknown", "unavailable", "none", ""}


def _parse_datetime(value: object, timezone: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("timestamp_invalid") from exc
    else:
        raise ValueError("timestamp_missing")  # noqa: TRY004
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp_naive")
    return parsed.astimezone(timezone)


def _parse_amount(value: object) -> Decimal:
    if isinstance(value, Mapping):
        value = value.get("amount")
    if isinstance(value, bool) or value is None:
        raise ValueError("price_amount_missing")
    try:
        return Decimal(str(value)) / _AMOUNT_SCALE
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("price_amount_invalid") from exc


def _invalid(retrieved_at: datetime | None, reason: str) -> PriceProviderState:
    return PriceProviderState(
        current=None,
        future=(),
        retrieved_at=retrieved_at,
        valid=False,
        error_reason=reason,
    )


def parse_zonneplan_entity(
    entity_state: Mapping[str, object],
    *,
    now: datetime,
    retrieved_at: datetime,
    timezone_name: str = "Europe/Amsterdam",
) -> PriceProviderState:
    """Normalize a captured Zonneplan quarter-hour tariff entity state.

    The upstream integration publishes forecast records under the entity's
    ``forecast`` attribute. Amounts are fixed-point integer values in units of
    1e-7 EUR/kWh; the tax-included amount is the planner input.
    """

    if now.tzinfo is None or now.utcoffset() is None:
        return _invalid(retrieved_at, "now_not_timezone_aware")
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        return _invalid(None, "retrieved_at_not_timezone_aware")
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return _invalid(retrieved_at, "timezone_invalid")

    state = str(entity_state.get("state", "")).lower()
    if state in _UNAVAILABLE_STATES:
        return _invalid(retrieved_at, "provider_unavailable")
    forecast = entity_state.get("attributes", {})
    if not isinstance(forecast, Mapping):
        return _invalid(retrieved_at, "attributes_invalid")
    forecast = forecast.get("forecast")
    if not isinstance(forecast, list) or not forecast:
        return _invalid(retrieved_at, "forecast_missing")

    intervals: list[PriceInterval] = []
    previous_end: datetime | None = None
    try:
        for item in forecast:
            if not isinstance(item, Mapping):
                raise ValueError("forecast_item_invalid")  # noqa: TRY004, TRY301
            start = _parse_datetime(item.get("start_date"), timezone)
            end = _parse_datetime(item.get("end_date"), timezone)
            if end <= start or end - start != _QUARTER_HOUR:
                raise ValueError("interval_not_quarter_hour")  # noqa: TRY301
            if previous_end is not None and start != previous_end:
                raise ValueError("forecast_gap_or_overlap")  # noqa: TRY301
            included = _parse_amount(item.get("price_tax_included"))
            excluded_value = item.get("price_tax_excluded")
            excluded = (
                _parse_amount(excluded_value) if excluded_value is not None else None
            )
            intervals.append(
                PriceInterval(
                    start=start,
                    end=end,
                    import_price=included,
                    export_price=None,
                    source="zonneplan_one",
                    retrieved_at=retrieved_at,
                    valid=True,
                    price_basis=PriceBasis.ALL_IN_IMPORT,
                    taxes_and_fees=(
                        included - excluded if excluded is not None else None
                    ),
                    tax_excluded_price=excluded,
                )
            )
            previous_end = end
    except ValueError as exc:
        return _invalid(retrieved_at, str(exc))

    now_local = now.astimezone(timezone)
    current = next(
        (
            interval
            for interval in intervals
            if interval.start <= now_local < interval.end
        ),
        None,
    )
    future = tuple(
        interval
        for interval in intervals
        if interval.end > now_local and interval != current
    )
    if not future and current is None:
        return _invalid(retrieved_at, "forecast_expired")
    return PriceProviderState(
        current=current,
        future=future,
        retrieved_at=retrieved_at,
        valid=True,
    )
