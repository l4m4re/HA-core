"""Typed, read-only Growatt feedback values used by the future EMS."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time
from enum import IntEnum


class PriorityMode(IntEnum):
    """Growatt hybrid priority mode values."""

    LOAD_FIRST = 0
    BATTERY_FIRST = 1
    GRID_FIRST = 2

    @property
    def state(self) -> str:
        """Return the stable public state value."""

        return self.name.lower()


@dataclass(frozen=True)
class PriorityWord:
    """A priority word retaining its raw value, including unknown values."""

    raw: int
    mode: PriorityMode | None

    @property
    def state(self) -> str:
        """Return a state that cannot hide an unsupported raw value."""

        return self.mode.state if self.mode is not None else f"unknown_{self.raw}"

    @property
    def valid(self) -> bool:
        """Whether the raw value is a documented priority mode."""

        return self.mode is not None

    def as_dict(self) -> dict[str, int | str | bool | None]:
        """Return bounded Home Assistant-friendly attributes."""

        return {
            "raw_value": self.raw,
            "mode": self.mode.state if self.mode is not None else None,
            "valid": self.valid,
        }


def decode_priority_word(raw: int) -> PriorityWord:
    """Decode I3144 without coercing reserved values."""

    return PriorityWord(raw=raw, mode=PriorityMode._value2member_map_.get(raw))


@dataclass(frozen=True)
class XhScheduleSlot:
    """One TL-XH schedule slot with exact source words retained."""

    slot: int
    start: time | None
    end: time | None
    priority: PriorityWord
    enabled: bool
    raw_start_word: int
    raw_end_word: int

    @property
    def valid(self) -> bool:
        """Whether the packed words contain supported values."""

        return self.priority.valid and self.start is not None and self.end is not None

    def as_dict(
        self,
    ) -> dict[str, int | str | bool | dict[str, int | str | bool | None]]:
        """Return bounded structured attributes for a HA state entity."""

        return {
            "slot": self.slot,
            "start": self.start.isoformat(timespec="minutes") if self.start else None,
            "end": self.end.isoformat(timespec="minutes") if self.end else None,
            "priority": self.priority.state,
            "priority_raw": self.priority.raw,
            "enabled": self.enabled,
            "raw_start_word": self.raw_start_word,
            "raw_end_word": self.raw_end_word,
            "valid": self.valid,
        }


_SCHEDULE_START_REGISTERS = (3038, 3040, 3042, 3044, 3050, 3052, 3054, 3056, 3058)


def _decode_time(raw: int) -> time | None:
    """Decode a Growatt packed hour/minute word."""

    hour = (raw >> 8) & 0x1F
    minute = raw & 0xFF
    if hour > 23 or minute > 59:
        return None
    return time(hour=hour, minute=minute)


def _decode_start(raw: int) -> tuple[time | None, PriorityWord, bool]:
    """Decode a packed XH schedule start/control word."""

    return (
        _decode_time(raw),
        decode_priority_word((raw >> 13) & 0x03),
        bool(raw & 0x8000),
    )


def decode_xh_schedule(registers: Mapping[int, int]) -> tuple[XhScheduleSlot, ...]:
    """Decode the nine TL-XH schedule slots from holding-register words."""

    slots: list[XhScheduleSlot] = []
    for slot, start_register in enumerate(_SCHEDULE_START_REGISTERS, start=1):
        raw_start = registers[start_register]
        raw_end = registers[start_register + 1]
        start, priority, enabled = _decode_start(raw_start)
        slots.append(
            XhScheduleSlot(
                slot=slot,
                start=start,
                end=_decode_time(raw_end),
                priority=priority,
                enabled=enabled,
                raw_start_word=raw_start,
                raw_end_word=raw_end,
            )
        )
    return tuple(slots)


def schedule_registers() -> tuple[int, ...]:
    """Return the exact holding registers needed for the nine XH slots."""

    return tuple(
        register
        for start in _SCHEDULE_START_REGISTERS
        for register in (start, start + 1)
    )
