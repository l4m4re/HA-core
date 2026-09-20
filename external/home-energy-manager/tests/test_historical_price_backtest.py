"""Exercise EMS price selection against curated historical examples."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
import json
from pathlib import Path
from typing import cast

from ems_contract.live_snapshot import load_snapshot
from ems_contract.planner import PlannerConfig, plan_shadow_ems
from ems_contract.providers import PriceBasis, PriceInterval, PriceProviderState
from ems_contract.snapshot import EmsSnapshot

ROOT = Path(__file__).parents[1]
INVENTORY = ROOT / "docs/HA-8C_LIVE_INPUT_INVENTORY.json"
HISTORICAL_EXAMPLES = ROOT / "ems_contract/data/price_history/curated_examples.json"


def _historical_case(selection_id: str) -> tuple[EmsSnapshot, PriceProviderState]:
    """Build a simulated planner input from one quarter-hour sample."""

    data = cast(dict[str, object], json.loads(HISTORICAL_EXAMPLES.read_text()))
    selections = cast(list[dict[str, object]], data["selections"])
    selection = next(item for item in selections if item["id"] == selection_id)
    interval_minutes = cast(int, selection["source_interval_minutes"])
    if interval_minutes != 15:
        raise ValueError("the shadow planner currently requires quarter-hour prices")
    rows = cast(list[dict[str, str]], selection["records"])

    starts = [
        datetime.fromisoformat(row["datum_utc"]).replace(tzinfo=UTC) for row in rows
    ]
    simulated_at = starts[0]
    intervals = tuple(
        PriceInterval(
            start=start,
            end=start + timedelta(minutes=interval_minutes),
            import_price=Decimal(row["prijs_excl_belastingen"].replace(",", ".")),
            export_price=None,
            source="curated_historical_archive",
            retrieved_at=simulated_at,
            valid=True,
            price_basis=PriceBasis.UNKNOWN,
        )
        for row, start in zip(rows, starts, strict=True)
    )
    if any(right.start != left.end for left, right in pairwise(intervals)):
        raise ValueError("historical sample contains a time gap or overlap")

    base = load_snapshot(INVENTORY)
    snapshot = replace(
        base,
        timestamp=simulated_at,
        growatt=replace(
            base.growatt,
            observed_at=simulated_at,
            priority_observed_at=simulated_at,
            schedule_observed_at=simulated_at,
        ),
    )
    return snapshot, PriceProviderState(
        current=None,
        future=intervals,
        retrieved_at=simulated_at,
        valid=True,
    )


def test_planner_finds_negative_price_pattern_in_historical_quarter_hours() -> None:
    """The planner can use recorded negative prices to select charging slots."""

    snapshot, price = _historical_case("quarter-hour-negative-prices-2025-05-11")
    plan = plan_shadow_ems(snapshot, PlannerConfig(), price=price)

    assert plan.valid
    assert len(plan.selected_cheap_intervals) == 11
    assert sum(item.import_price < 0 for item in price.future) > len(
        plan.selected_cheap_intervals
    )
    assert all(
        item.import_price is not None and item.import_price < 0
        for item in plan.selected_cheap_intervals
    )


def test_planner_ranks_historical_intraday_prices_by_cost() -> None:
    """A volatile historical day still selects its cheapest charge intervals."""

    snapshot, price = _historical_case("quarter-hour-wide-range-2026-06-24")
    plan = plan_shadow_ems(snapshot, PlannerConfig(), price=price)

    assert plan.valid
    selected_prices = sorted(
        item.import_price for item in plan.selected_cheap_intervals
    )
    all_prices = sorted(item.import_price for item in price.future)
    assert selected_prices == all_prices[: len(selected_prices)]
