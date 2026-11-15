"""Execute bounded original ZABA22 ARM/Thumb fragments offline with Unicorn."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Any

from unicorn import (
    Uc,
    UcError,
    UC_ARCH_ARM,
    UC_HOOK_CODE,
    UC_HOOK_MEM_READ,
    UC_HOOK_MEM_READ_UNMAPPED,
    UC_HOOK_MEM_WRITE,
    UC_HOOK_MEM_WRITE_UNMAPPED,
    UC_MODE_THUMB,
)
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R13

FLASH_BASE = 0x08000000
FLASH_SIZE = 0x40000
RAM_BASE = 0x20000000
RAM_SIZE = 0x10000
MMIO_BASE = 0x40000000
MMIO_SIZE = 0x100000
RETURN_STUB = RAM_BASE + 0x8000
STACK_TOP = RAM_BASE + 0xF000
INPUT_BASE = RAM_BASE + 0x1000
CRC_LOW_TABLE = RAM_BASE + 0x53B0
CRC_HIGH_TABLE = RAM_BASE + 0x54B0
RESET_HANDLER = 0x08003510
CRC16_FUNCTION = 0x080130BC
BYTE_SUM_FUNCTION = 0x080130EA
EXPECTED_PAYLOAD_SHA256 = "97c22678f14e490a748df03ea1c9d2940a74a1dd239d45e290a0843dab90c858"


@dataclass(frozen=True)
class ExecutionResult:
    function: int
    input_hex: str
    output: int | None
    original_bytes: bool
    image_sha256: str
    trace: tuple[tuple[int, int], ...]
    mmio_events: tuple[dict[str, int | str], ...]
    stop_reason: str
    error: str | None

    @property
    def trace_digest(self) -> str:
        encoded = json.dumps(self.trace, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


def payload_path() -> Path:
    return Path(__file__).parents[2] / "external/growatt-firmware/ALBA18/ZABA22-payload.bin"


def load_payload(path: Path | None = None) -> bytes:
    payload = (path or payload_path()).read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_PAYLOAD_SHA256:
        raise ValueError(f"unexpected ZABA22 payload hash: {digest}")
    if len(payload) != FLASH_SIZE:
        raise ValueError(f"unexpected ZABA22 payload size: {len(payload)}")
    return payload


def _crc_tables() -> tuple[bytes, bytes]:
    low = bytearray(256)
    high = bytearray(256)
    for index in range(256):
        crc = index
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        low[index] = crc & 0xFF
        high[index] = crc >> 8
    return bytes(low), bytes(high)


def _map_common(uc: Uc, payload: bytes) -> None:
    uc.mem_map(FLASH_BASE, FLASH_SIZE)
    uc.mem_write(FLASH_BASE, payload)
    uc.mem_map(RAM_BASE, RAM_SIZE)
    uc.mem_write(RETURN_STUB, b"\x70\x47")


def _result(
    *,
    function: int,
    data: bytes,
    payload: bytes,
    trace: list[tuple[int, int]],
    mmio_events: list[dict[str, int | str]],
    output: int | None,
    stop_reason: str,
    error: str | None,
) -> ExecutionResult:
    return ExecutionResult(
        function=function,
        input_hex=data.hex(),
        output=output,
        original_bytes=True,
        image_sha256=hashlib.sha256(payload).hexdigest(),
        trace=tuple(trace),
        mmio_events=tuple(mmio_events),
        stop_reason=stop_reason,
        error=error,
    )


def execute_original(function: int, data: bytes, *, seed_crc_tables: bool = False, max_instructions: int = 100_000) -> ExecutionResult:
    """Execute one original function; all executable instructions come from the payload."""

    payload = load_payload()
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    _map_common(uc, payload)
    trace: list[tuple[int, int]] = []
    mmio_events: list[dict[str, int | str]] = []
    uc.mem_write(INPUT_BASE, data)
    if seed_crc_tables:
        low, high = _crc_tables()
        uc.mem_write(CRC_LOW_TABLE, low)
        uc.mem_write(CRC_HIGH_TABLE, high)

    return_hit = False

    def code_hook(_uc: Uc, address: int, size: int, _user_data: Any) -> None:
        nonlocal return_hit
        pc = address & ~1
        trace.append((pc, size))
        if pc == RETURN_STUB:
            return_hit = True
            _uc.emu_stop()

    def mmio_hook(_uc: Uc, access: int, address: int, size: int, value: int, _user_data: Any) -> None:
        mmio_events.append({"access": access, "address": address, "size": size, "value": value})
        _uc.emu_stop()

    def unmapped_hook(_uc: Uc, access: int, address: int, size: int, value: int, _user_data: Any) -> bool:
        mmio_events.append({"access": access, "address": address, "size": size, "value": value})
        _uc.emu_stop()
        return False

    uc.hook_add(UC_HOOK_CODE, code_hook)
    uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, mmio_hook, begin=MMIO_BASE, end=MMIO_BASE + MMIO_SIZE - 1)
    uc.hook_add(UC_HOOK_MEM_READ_UNMAPPED | UC_HOOK_MEM_WRITE_UNMAPPED, unmapped_hook)

    uc.reg_write(UC_ARM_REG_R0, INPUT_BASE)
    uc.reg_write(UC_ARM_REG_R1, len(data))
    uc.reg_write(UC_ARM_REG_R13, STACK_TOP)
    uc.reg_write(UC_ARM_REG_LR, RETURN_STUB | 1)
    error: str | None = None
    stop_reason = "instruction_limit"
    try:
        uc.emu_start(function | 1, RETURN_STUB | 1, count=max_instructions)
    except UcError as exc:
        error = str(exc)
        stop_reason = "emulator_error"
    if mmio_events:
        stop_reason = "mmio_blocker"
    elif return_hit:
        stop_reason = "return_stub"
    output = uc.reg_read(UC_ARM_REG_R0) if stop_reason == "return_stub" else None
    return _result(function=function, data=data, payload=payload, trace=trace, mmio_events=mmio_events, output=output, stop_reason=stop_reason, error=error)


def execute_reset_probe(*, max_instructions: int = 200) -> ExecutionResult:
    """Run the original reset handler until its first unsupported MMIO access."""

    payload = load_payload()
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    _map_common(uc, payload)
    trace: list[tuple[int, int]] = []
    mmio_events: list[dict[str, int | str]] = []

    def code_hook(_uc: Uc, address: int, size: int, _user_data: Any) -> None:
        trace.append((address & ~1, size))

    def unmapped_hook(_uc: Uc, access: int, address: int, size: int, value: int, _user_data: Any) -> bool:
        mmio_events.append({"access": access, "address": address, "size": size, "value": value})
        _uc.emu_stop()
        return False

    uc.hook_add(UC_HOOK_CODE, code_hook)
    uc.hook_add(UC_HOOK_MEM_READ_UNMAPPED | UC_HOOK_MEM_WRITE_UNMAPPED, unmapped_hook)
    initial_sp = int.from_bytes(payload[0:4], "little")
    reset = int.from_bytes(payload[4:8], "little") & ~1
    uc.reg_write(UC_ARM_REG_R13, initial_sp)
    error: str | None = None
    try:
        uc.emu_start(reset | 1, 0, count=max_instructions)
    except UcError as exc:
        error = str(exc)
    stop_reason = "emulator_error" if error else "instruction_limit"
    if mmio_events:
        stop_reason = "mmio_blocker"
    return _result(function=reset, data=b"", payload=payload, trace=trace, mmio_events=mmio_events, output=None, stop_reason=stop_reason, error=error)


def backend_availability() -> dict[str, object]:
    return {
        "unicorn": True,
        "qemu_system_arm": which("qemu-system-arm") is not None,
        "qemu_arm": which("qemu-arm") is not None,
        "renode": which("renode") is not None,
        "dotnet": which("dotnet") is not None,
        "gdb": which("gdb") is not None,
        "gdb_multiarch": which("gdb-multiarch") is not None,
    }
