"""Create a sanitized, downsampled replay set from local PyCanZE captures."""

import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

from .zoe_prediction import (
    CURRENT_SETTINGS_A,
    ZoeChargeSample,
    load_poller_csv,
    split_charge_sessions,
)

SAMPLE_INTERVAL = timedelta(minutes=5)
MINIMUM_DURATION = timedelta(minutes=30)
MINIMUM_SOC_GAIN_PCT = 1.0


def _recognized_setting(samples: tuple[ZoeChargeSample, ...]) -> bool:
    currents = [sample.current_a for sample in samples if sample.current_a is not None]
    if not currents:
        return False
    observed = median(currents)
    setting = min(CURRENT_SETTINGS_A, key=lambda item: abs(item - observed))
    return abs(setting - observed) <= setting * 0.25


def _is_usable_session(
    samples: tuple[ZoeChargeSample, ...], *, maximum_session_soc_pct: float | None
) -> bool:
    points = [sample for sample in samples if sample.soc_pct is not None]
    return (
        len(points) >= 3
        and points[-1].timestamp - points[0].timestamp >= MINIMUM_DURATION
        and points[-1].soc_pct - points[0].soc_pct >= MINIMUM_SOC_GAIN_PCT
        and (
            maximum_session_soc_pct is None
            or points[-1].soc_pct <= maximum_session_soc_pct
        )
        and _recognized_setting(samples)
    )


def _downsample(samples: tuple[ZoeChargeSample, ...]) -> tuple[ZoeChargeSample, ...]:
    points = [sample for sample in samples if sample.soc_pct is not None]
    selected: list[ZoeChargeSample] = []
    next_sample_at: datetime | None = None
    for sample in points:
        if next_sample_at is None or sample.timestamp >= next_sample_at:
            selected.append(sample)
            next_sample_at = sample.timestamp + SAMPLE_INTERVAL
    if points and selected[-1] is not points[-1]:
        selected.append(points[-1])
    return tuple(selected)


def _csv_inputs(paths: list[Path], excluded: set[Path]) -> tuple[Path, ...]:
    found: set[Path] = set()
    for path in paths:
        candidates = path.glob("*.csv") if path.is_dir() else (path,)
        found.update(
            candidate.resolve()
            for candidate in candidates
            if candidate.suffix == ".csv"
        )
    return tuple(sorted(found - excluded))


def curate_replay_samples(
    input_paths: list[Path],
    *,
    excluded_paths: set[Path] | None = None,
    maximum_session_soc_pct: float | None = None,
) -> tuple[ZoeChargeSample, ...]:
    """Collect usable sessions, then remove source dates and over-dense polls."""

    sessions: list[tuple[ZoeChargeSample, ...]] = []
    excluded = {path.resolve() for path in excluded_paths or set()}
    for path in _csv_inputs(input_paths, excluded):
        sessions.extend(
            session
            for session in split_charge_sessions(load_poller_csv(path))
            if _is_usable_session(
                session, maximum_session_soc_pct=maximum_session_soc_pct
            )
        )

    output: list[ZoeChargeSample] = []
    synthetic_date = datetime(2026, 1, 1)
    for session in sessions:
        points = _downsample(session)
        source_start = points[0].timestamp
        output.extend(
            ZoeChargeSample(
                timestamp=synthetic_date + (sample.timestamp - source_start),
                charging=True,
                soc_pct=sample.soc_pct,
                current_a=sample.current_a,
                power_w=sample.power_w,
            )
            for sample in points
        )
        synthetic_date += timedelta(days=1)
    return tuple(output)


def main() -> None:
    """Write the selected charging fields without vehicle metadata or dates."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", type=Path, required=True)
    parser.add_argument("--exclude", action="append", type=Path, default=[])
    parser.add_argument("--maximum-session-soc", type=float)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    samples = curate_replay_samples(
        args.inputs,
        excluded_paths=set(args.exclude),
        maximum_session_soc_pct=args.maximum_session_soc,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(("timestamp", "charging", "soc_pct", "current_a", "power_w"))
        for sample in samples:
            writer.writerow(
                (
                    sample.timestamp.isoformat(),
                    "true",
                    f"{sample.soc_pct:.2f}" if sample.soc_pct is not None else "",
                    f"{sample.current_a:.1f}" if sample.current_a is not None else "",
                    f"{sample.power_w:.0f}" if sample.power_w is not None else "",
                )
            )


if __name__ == "__main__":
    main()
