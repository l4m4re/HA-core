"""Execute selected ZABA22 VPP paths without replacing them with a model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from unicorn import Uc, UcError, UC_ARCH_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_MODE_THUMB
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_R13

from ..harness import (
    FLASH_BASE,
    FLASH_SIZE,
    RAM_BASE,
    RAM_SIZE,
    RETURN_STUB,
    STACK_TOP,
    load_payload,
)

H30100 = 0x2000ABA4
H3037 = 0x2000E54E
H30475 = 0x2000AE92
BRIDGE_LATCH = 0x2000E6EB
PENDING_MASK = 0x2000EB64
DIRTY_MASK = 0x2000EB60
RESPONSE = 0x200092C4

BRIDGE = 0x0801474C
BRIDGE_STOP = 0x0801491E
FC06_PENDING_CHECK = 0x0801E990
FC06_PENDING_STOP = 0x0801E9BC


@dataclass(frozen=True)
class MemoryWrite:
    address: int
    size: int
    value: int


@dataclass(frozen=True)
class OriginalPathResult:
    path: str
    fixture: dict[str, int]
    stop_pc: int | None
    stop_reason: str
    writes: tuple[MemoryWrite, ...]
    trace: tuple[int, ...]
    response: bytes
    error: str | None


def _u16(uc: Uc, address: int) -> int:
    return int.from_bytes(uc.mem_read(address, 2), "little")


def _u32(uc: Uc, address: int) -> int:
    return int.from_bytes(uc.mem_read(address, 4), "little")


def _put16(uc: Uc, address: int, value: int) -> None:
    uc.mem_write(address, (value & 0xFFFF).to_bytes(2, "little"))


def _put32(uc: Uc, address: int, value: int) -> None:
    uc.mem_write(address, (value & 0xFFFFFFFF).to_bytes(4, "little"))


def _base_uc() -> Uc:
    payload = load_payload()
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    uc.mem_map(FLASH_BASE, FLASH_SIZE)
    uc.mem_write(FLASH_BASE, payload)
    uc.mem_map(RAM_BASE, RAM_SIZE)
    uc.mem_write(RETURN_STUB, b"\x70\x47")
    return uc


def _install_bridge_fixture(uc: Uc, *, h30100: int, h3037: int, latch: int) -> None:
    # These are the literal-pointer targets used by the original function.
    _put16(uc, H30100, h30100)
    uc.mem_write(H3037, bytes((h3037 & 0xFF,)))
    uc.mem_write(BRIDGE_LATCH, bytes((latch & 0xFF,)))
    _put16(uc, H30475, 0)
    _put32(uc, DIRTY_MASK, 0)
    _put32(uc, 0x2000AADC + 0xC8, h30100)
    _put16(uc, 0x2000AADC + 0x3B6, 0)


def execute_bridge(*, h30100: int, h3037: int, latch: int, max_instructions: int = 20_000) -> OriginalPathResult:
    """Run the original bridge until its natural common-return PC."""

    uc = _base_uc()
    _install_bridge_fixture(uc, h30100=h30100, h3037=h3037, latch=latch)
    trace: list[int] = []
    writes: list[MemoryWrite] = []
    stop_pc: int | None = None

    def code_hook(_uc: Uc, address: int, _size: int, _user_data: Any) -> None:
        nonlocal stop_pc
        pc = address & ~1
        trace.append(pc)
        if pc == BRIDGE_STOP:
            stop_pc = pc
            _uc.emu_stop()

    def write_hook(_uc: Uc, _access: int, address: int, size: int, value: int, _user_data: Any) -> None:
        if RAM_BASE <= address < RAM_BASE + RAM_SIZE:
            writes.append(MemoryWrite(address, size, value))

    uc.hook_add(UC_HOOK_CODE, code_hook)
    uc.hook_add(UC_HOOK_MEM_WRITE, write_hook, begin=RAM_BASE, end=RAM_BASE + RAM_SIZE - 1)
    uc.reg_write(UC_ARM_REG_R13, STACK_TOP)
    uc.reg_write(UC_ARM_REG_LR, RETURN_STUB | 1)
    error: str | None = None
    try:
        uc.emu_start(BRIDGE | 1, RETURN_STUB | 1, count=max_instructions)
    except UcError as exc:
        error = str(exc)
    if error:
        reason = "emulator_error"
    elif stop_pc is not None:
        reason = "natural_bridge_stop"
    else:
        reason = "instruction_limit"
    return OriginalPathResult(
        path="FUN_0801474C",
        fixture={"H30100": h30100, "H3037": h3037, "bridge_latch": latch},
        stop_pc=stop_pc,
        stop_reason=reason,
        writes=tuple(writes),
        trace=tuple(trace),
        response=b"",
        error=error,
    )

def execute_fc06_pending_gate(*, pending_mask: int, max_instructions: int = 200) -> OriginalPathResult:
    """Run the original FC06 pending-mask check through response construction."""

    uc = _base_uc()
    _put32(uc, PENDING_MASK, pending_mask)
    uc.mem_write(RESPONSE, b"\x00" * 8)
    trace: list[int] = []
    writes: list[MemoryWrite] = []
    stop_pc: int | None = None

    def code_hook(_uc: Uc, address: int, _size: int, _user_data: Any) -> None:
        nonlocal stop_pc
        pc = address & ~1
        trace.append(pc)
        if pc == FC06_PENDING_STOP:
            stop_pc = pc
            _uc.emu_stop()

    def write_hook(_uc: Uc, _access: int, address: int, size: int, value: int, _user_data: Any) -> None:
        if RAM_BASE <= address < RAM_BASE + RAM_SIZE:
            writes.append(MemoryWrite(address, size, value))

    uc.hook_add(UC_HOOK_CODE, code_hook)
    uc.hook_add(UC_HOOK_MEM_WRITE, write_hook, begin=RAM_BASE, end=RAM_BASE + RAM_SIZE - 1)
    uc.reg_write(UC_ARM_REG_R13, STACK_TOP)
    uc.reg_write(UC_ARM_REG_LR, RETURN_STUB | 1)
    error: str | None = None
    try:
        uc.emu_start(FC06_PENDING_CHECK | 1, RETURN_STUB | 1, count=max_instructions)
    except UcError as exc:
        error = str(exc)
    if error:
        reason = "emulator_error"
    elif stop_pc is not None:
        reason = "pending_response_stop"
    else:
        reason = "instruction_limit"
    return OriginalPathResult(
        path="FC06 pending pre-gate",
        fixture={"pending_mask": pending_mask},
        stop_pc=stop_pc,
        stop_reason=reason,
        writes=tuple(writes),
        trace=tuple(trace),
        response=bytes(uc.mem_read(RESPONSE, 8)),
        error=error,
    )
