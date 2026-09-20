"""Run the HA-8D planner against local sanitized fixtures only."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

from .live_snapshot import load_snapshot
from .planner import PlannerConfig, ShadowMode, plan_shadow_ems
from .zonneplan import parse_zonneplan_entity


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as input_file:
        return json.load(input_file)


def main() -> None:
    """Print a deterministic JSON shadow plan."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--prices", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--mode",
        type=ShadowMode,
        default=ShadowMode.CHEAP_CHARGE,
        choices=list(ShadowMode),
    )
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    snapshot = load_snapshot(args.inventory)
    price_fixture = _load_json(args.prices)
    retrieved_at = datetime.fromisoformat(price_fixture["retrieved_at"])
    prices = parse_zonneplan_entity(
        price_fixture["entity"],
        now=snapshot.timestamp,
        retrieved_at=retrieved_at,
        timezone_name=price_fixture.get("timezone", "Europe/Amsterdam"),
    )
    config = (
        PlannerConfig.from_mapping(_load_json(args.config))
        if args.config
        else PlannerConfig()
    )
    plan = plan_shadow_ems(
        snapshot,
        config,
        requested_mode=args.mode,
        price=prices,
    )
    if args.summary:
        sys.stdout.write(
            f"mode={plan.mode.value} valid={plan.valid} soc={plan.current_soc} "
            f"selected_intervals={len(plan.selected_cheap_intervals)} "
            f"candidate_windows={len(plan.growatt_candidate_windows)} "
            f"hypothetical_writes={plan.hypothetical_write_count}\n"
        )
    sys.stdout.write(json.dumps(plan.as_dict(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
