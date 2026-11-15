"""Executable contract for the original ZABA22 startup boundary.

This module records facts derived from the original vector table separately
from state supplied by a system emulator or loader.  It intentionally models
loader placement and memory ownership, not STM32 peripheral behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from research.zaba22_original_rehosting.harness import (
    EXPECTED_PAYLOAD_SHA256,
    FLASH_BASE,
    FLASH_SIZE,
    RAM_BASE,
    RAM_SIZE,
    execute_reset_probe,
    load_payload,
    payload_path,
)

VECTOR_SIZE = 8
VTOR_ADDRESS = 0xE000ED08
EXPECTED_INITIAL_SP = 0x20000CF8
EXPECTED_RESET_RAW = 0x08003511
EXPECTED_RESET_PC = 0x08003510
RESET_PROBE_PC = 0x080020BC
RCC_ADDRESS = 0x40021000


class ContractError(ValueError):
    """The image or loader state violates the startup contract."""


class StateOrigin(StrEnum):
    """Provenance of a state snapshot."""

    FIRMWARE_VECTOR = "firmware-vector"
    EMULATOR_PROVIDED = "emulator-provided"


@dataclass(frozen=True)
class MemoryRegion:
    """A deliberately small region map used by the loader contract."""

    name: str
    base: int
    size: int

    def contains(self, address: int, width: int = 1) -> bool:
        if width <= 0:
            raise ContractError("memory access width must be positive")
        return self.base <= address and address + width <= self.base + self.size


@dataclass(frozen=True)
class FirmwareStartupState:
    """State read from the original image's vector table."""

    initial_sp: int
    reset_raw: int
    reset_pc: int
    thumb: bool
    origin: StateOrigin = StateOrigin.FIRMWARE_VECTOR


@dataclass(frozen=True)
class EmulatorStartupState:
    """State supplied to the emulated CPU; it is not firmware execution."""

    initial_sp: int
    reset_pc: int
    thumb: bool
    vtor: int
    origin: StateOrigin = StateOrigin.EMULATOR_PROVIDED


@dataclass(frozen=True)
class LoaderContract:
    """QEMU loader assumptions used by the phase-2 system-emulator runner."""

    image: Path
    flash_base: int = FLASH_BASE
    vtor_address: int = VTOR_ADDRESS
    vtor_value: int = FLASH_BASE

    def qemu_arguments(self) -> tuple[str, ...]:
        return (
            "-device",
            f"loader,file={self.image},addr={self.flash_base:#x}",
            "-device",
            f"loader,addr={self.vtor_address:#x},data={self.vtor_value:#x},data-len=4",
        )

    def validate(self, *, image_size: int = FLASH_SIZE) -> None:
        if not self.image.name:
            raise ContractError("loader image must name a file")
        if image_size != FLASH_SIZE:
            raise ContractError(f"loader image size must be {FLASH_SIZE:#x} bytes")
        if self.flash_base != FLASH_BASE:
            raise ContractError("image must be placed at the original flash base")
        if self.vtor_address != VTOR_ADDRESS or self.vtor_value != FLASH_BASE:
            raise ContractError("loader VTOR write must select the original flash")


FLASH_REGION = MemoryRegion("original-flash", FLASH_BASE, FLASH_SIZE)
RAM_REGION = MemoryRegion("ram", RAM_BASE, RAM_SIZE)


def firmware_startup_state(payload: bytes) -> FirmwareStartupState:
    """Read and validate the original initial SP and reset vector."""

    if len(payload) < VECTOR_SIZE:
        raise ContractError("payload is shorter than the reset vector")
    initial_sp = int.from_bytes(payload[0:4], "little")
    reset_raw = int.from_bytes(payload[4:8], "little")
    if not RAM_REGION.contains(initial_sp, 4) or initial_sp % 4:
        raise ContractError(f"invalid vector initial SP: {initial_sp:#x}")
    if not FLASH_REGION.contains(reset_raw & ~1, 2):
        raise ContractError(f"reset vector is outside flash: {reset_raw:#x}")
    if not reset_raw & 1:
        raise ContractError("reset vector does not select Thumb state")
    return FirmwareStartupState(initial_sp, reset_raw, reset_raw & ~1, True)


def emulator_startup_state(
    *, initial_sp: int, reset_pc: int, thumb: bool, vtor: int = FLASH_BASE
) -> EmulatorStartupState:
    """Validate state supplied by a loader without attributing it to firmware."""

    if not RAM_REGION.contains(initial_sp, 4) or initial_sp % 4:
        raise ContractError(f"invalid emulator SP: {initial_sp:#x}")
    if not FLASH_REGION.contains(reset_pc, 2) or reset_pc & 1:
        raise ContractError(f"invalid emulator PC: {reset_pc:#x}")
    if not thumb:
        raise ContractError("original reset must execute in Thumb state")
    if vtor != FLASH_BASE:
        raise ContractError(f"unexpected VTOR: {vtor:#x}")
    return EmulatorStartupState(initial_sp, reset_pc, thumb, vtor)


def collect_startup_evidence(*, max_instructions: int = 200) -> dict[str, object]:
    """Run the existing bounded reset probe and return contract evidence."""

    if max_instructions <= 0:
        raise ContractError("startup probe instruction bound must be positive")
    payload = load_payload()
    firmware = firmware_startup_state(payload)
    loader = LoaderContract(payload_path())
    loader.validate(image_size=len(payload))
    emulator = emulator_startup_state(
        initial_sp=firmware.initial_sp,
        reset_pc=firmware.reset_pc,
        thumb=firmware.thumb,
    )
    execution = execute_reset_probe(max_instructions=max_instructions)
    return {
        "payload_sha256": EXPECTED_PAYLOAD_SHA256,
        "firmware_state": firmware,
        "emulator_state": emulator,
        "loader": loader,
        "stop_reason": execution.stop_reason,
        "stop_pc": execution.trace[-1][0] if execution.trace else None,
        "mmio_events": execution.mmio_events,
        "bounded": len(execution.trace) <= max_instructions,
    }
