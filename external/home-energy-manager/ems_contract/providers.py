"""Typed read-only provider contracts for the future EMS."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol


class PriceBasis(StrEnum):
    """Meaning of the price fields supplied by a provider."""

    ALL_IN_IMPORT = "all_in_import"
    COMMODITY = "commodity"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PriceInterval:
    """One normalized price interval; no economic decision is implied."""

    start: datetime
    end: datetime
    import_price: Decimal | None
    export_price: Decimal | None
    source: str
    retrieved_at: datetime
    valid: bool
    price_basis: PriceBasis = PriceBasis.UNKNOWN
    commodity_price: Decimal | None = None
    taxes_and_fees: Decimal | None = None
    error_reason: str | None = None
    tax_excluded_price: Decimal | None = None


@dataclass(frozen=True)
class PriceProviderState:
    """Current and future price data with explicit validity and age source."""

    current: PriceInterval | None
    future: tuple[PriceInterval, ...]
    retrieved_at: datetime | None
    valid: bool
    error_reason: str | None = None


class PriceProvider(Protocol):
    """Read-only interface implemented by a tariff adapter."""

    async def async_get_price_state(self) -> PriceProviderState:
        """Return normalized current and future price intervals."""


@dataclass(frozen=True)
class FixturePriceProvider:
    """Deterministic read-only provider for contract and planner tests."""

    state: PriceProviderState

    async def async_get_price_state(self) -> PriceProviderState:
        """Return the fixture state without contacting a service."""

        return self.state


class EvAvailability(StrEnum):
    """Distinguish unavailable data from a measured disconnected EV."""

    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"
    AVAILABLE = "available"


@dataclass(frozen=True)
class EvProviderState:
    """Partial EV/charger state; absent fields are not fabricated as zero."""

    availability: EvAvailability
    observed_at: datetime | None
    connected: bool | None = None
    charging: bool | None = None
    current_limit_a: float | None = None
    charging_power_w: float | None = None
    soc_pct: float | None = None
    target_soc_pct: float | None = None
    departure: datetime | None = None
    soc_observed_at: datetime | None = None
    valid: bool = False
    error_reason: str | None = None


class EvProvider(Protocol):
    """Read-only interface for Peblar, Zoe, or another EV provider."""

    async def async_get_ev_state(self) -> EvProviderState:
        """Return partial EV state without issuing commands."""


@dataclass(frozen=True)
class FixtureEvProvider:
    """Deterministic read-only EV provider for contract tests."""

    state: EvProviderState

    async def async_get_ev_state(self) -> EvProviderState:
        """Return the fixture state without issuing an EV command."""

        return self.state
