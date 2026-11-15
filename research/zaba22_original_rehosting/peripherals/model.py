"""Small, evidence-bounded RCC/FLASH/VTOR peripheral model.

This is a reusable contract for trace replay, not a firmware replacement.  The
F105/F107 values are candidate SVD evidence from P1; the exact ZABA22
derivative is intentionally not selected.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

RCC_BASE = 0x40021000
FLASH_BASE = 0x40022000
VTOR_ADDRESS = 0xE000ED08

RCC_CR = RCC_BASE + 0x00
RCC_CFGR = RCC_BASE + 0x04
RCC_CIR = RCC_BASE + 0x08
RCC_CFGR2 = RCC_BASE + 0x2C
FLASH_ACR = FLASH_BASE + 0x00

RCC_CR_RESET = 0x00000083
RCC_CFGR_RESET = 0x00000000
RCC_CIR_RESET = 0x00000000
RCC_CFGR2_RESET = 0x00000000
FLASH_ACR_RESET = 0x00000030
VTOR_RESET = 0x00000000

# Writable fields from the F105/F107 candidate SVDs.  Ready/status fields are
# deliberately excluded; they are driven by PollState, never by writes.
RCC_CR_WRITE_MASK = 0x150D00F9
RCC_CFGR_WRITE_MASK = 0x0F7FFFF3
RCC_CIR_WRITE_MASK = 0x00007F00
RCC_CIR_CLEAR_MASK = 0x00FF0000
RCC_CFGR2_WRITE_MASK = 0x0007FFFF
FLASH_ACR_WRITE_MASK = 0x0000001F
VTOR_WRITE_MASK = 0xFFFFFF80

HSE_ON = 1 << 16
HSE_READY = 1 << 17
PLL_ON = 1 << 24
PLL_READY = 1 << 25
SWS_MASK = 0b11 << 2
HSERDY_FLAG = 1 << 3
PLLRDY_FLAG = 1 << 4
HSERDY_CLEAR = 1 << 19
PLLRDY_CLEAR = 1 << 20


class AccessDirection(StrEnum):
    READ = "read"
    WRITE = "write"


class PeripheralBlocker(RuntimeError):
    """A typed boundary where the evidence does not justify progress."""


class UnsupportedMMIO(PeripheralBlocker):
    """An address, width, or access direction outside this contract."""

    def __init__(
        self,
        address: int,
        width: int,
        direction: AccessDirection,
        pc: int | None,
        evidence_needed: str,
    ) -> None:
        self.address = address
        self.width = width
        self.direction = direction
        self.pc = pc
        self.evidence_needed = evidence_needed
        super().__init__(
            f"unsupported MMIO {direction} address={address:#x} width={width} "
            f"pc={pc!r}; evidence needed: {evidence_needed}"
        )


class HSETimeout(PeripheralBlocker):
    """The firmware-bounded HSE ready wait did not complete."""

    def __init__(self, max_polls: int, elapsed_ticks: int) -> None:
        self.max_polls = max_polls
        self.elapsed_ticks = elapsed_ticks
        super().__init__(
            f"HSE ready timeout after {max_polls} polls and {elapsed_ticks} ticks"
        )


class UnboundedPollBlocker(PeripheralBlocker):
    """A PLL/SWS wait has no firmware timeout and cannot be guessed bounded."""

    def __init__(self, register: str, bit_or_mask: int, pc: int | None) -> None:
        self.register = register
        self.bit_or_mask = bit_or_mask
        self.pc = pc
        super().__init__(
            f"unbounded poll for {register} mask={bit_or_mask:#x} pc={pc!r}; "
            "additional evidence or an explicit emulator policy is required"
        )


@dataclass(frozen=True)
class TraceEvent:
    sequence: int
    operation: str
    address: int | None
    width: int | None
    value: int | None
    pc: int | None


@dataclass
class PollState:
    """Synthetic timing and status, separate from register storage."""

    elapsed_ticks: int = 0
    hse_polls: int = 0
    hse_ready_after_polls: int | None = 0
    hse_ready: bool = False
    pll_ready: bool = False
    sws: int = 0
    cir_flags: int = 0


class TraceDrivenPeripherals:
    """Model only the RCC/FLASH/VTOR contract justified by P1 evidence."""

    def __init__(self, *, hse_ready_after_polls: int | None = 0) -> None:
        if hse_ready_after_polls is not None and hse_ready_after_polls < 0:
            raise ValueError("HSE ready transition must not precede polling")
        self.poll_state = PollState(hse_ready_after_polls=hse_ready_after_polls)
        self._registers = {
            RCC_CR: RCC_CR_RESET,
            RCC_CFGR: RCC_CFGR_RESET,
            RCC_CIR: RCC_CIR_RESET,
            RCC_CFGR2: RCC_CFGR2_RESET,
            FLASH_ACR: FLASH_ACR_RESET,
            VTOR_ADDRESS: VTOR_RESET,
        }
        self.trace: list[TraceEvent] = []

    def _trace(
        self,
        operation: str,
        address: int | None,
        width: int | None,
        value: int | None,
        pc: int | None,
    ) -> None:
        self.trace.append(TraceEvent(len(self.trace), operation, address, width, value, pc))

    def _validate(self, address: int, width: int, direction: AccessDirection, pc: int | None) -> None:
        if width != 4 or address % 4:
            raise UnsupportedMMIO(address, width, direction, pc, "firmware trace and exact derivative register semantics")
        if address not in self._registers:
            raise UnsupportedMMIO(address, width, direction, pc, "firmware access evidence for this MMIO address")

    def _rcc_cr_value(self) -> int:
        value = self._registers[RCC_CR]
        value = (value | (1 << 1)) if self.poll_state.hse_ready is False else value
        value = (value | HSE_READY) if self.poll_state.hse_ready else (value & ~HSE_READY)
        value = (value | PLL_READY) if self.poll_state.pll_ready else (value & ~PLL_READY)
        return value

    def _rcc_cfgr_value(self) -> int:
        return (self._registers[RCC_CFGR] & ~SWS_MASK) | (self.poll_state.sws << 2)

    def read(self, address: int, *, width: int = 4, pc: int | None = None) -> int:
        self._validate(address, width, AccessDirection.READ, pc)
        if address == RCC_CR:
            value = self._rcc_cr_value()
        elif address == RCC_CFGR:
            value = self._rcc_cfgr_value()
        elif address == RCC_CIR:
            value = self._registers[address] | self.poll_state.cir_flags
        else:
            value = self._registers[address]
        self._trace("read", address, width, value, pc)
        return value

    def write(self, address: int, value: int, *, width: int = 4, pc: int | None = None) -> None:
        self._validate(address, width, AccessDirection.WRITE, pc)
        if not 0 <= value <= 0xFFFFFFFF:
            raise ValueError("MMIO value must be a uint32")
        if address == RCC_CR:
            self._registers[address] = (self._registers[address] & ~RCC_CR_WRITE_MASK) | (value & RCC_CR_WRITE_MASK)
            if not value & HSE_ON:
                self.poll_state.hse_ready = False
                self.poll_state.hse_polls = 0
        elif address == RCC_CFGR:
            self._registers[address] = (self._registers[address] & ~RCC_CFGR_WRITE_MASK) | (value & RCC_CFGR_WRITE_MASK)
        elif address == RCC_CIR:
            self._registers[address] = (self._registers[address] & ~RCC_CIR_WRITE_MASK) | (value & RCC_CIR_WRITE_MASK)
            if value & HSERDY_CLEAR:
                self.poll_state.cir_flags &= ~HSERDY_FLAG
            if value & PLLRDY_CLEAR:
                self.poll_state.cir_flags &= ~PLLRDY_FLAG
        elif address == RCC_CFGR2:
            self._registers[address] = (self._registers[address] & ~RCC_CFGR2_WRITE_MASK) | (value & RCC_CFGR2_WRITE_MASK)
        elif address == FLASH_ACR:
            self._registers[address] = (self._registers[address] & ~FLASH_ACR_WRITE_MASK) | (value & FLASH_ACR_WRITE_MASK)
        elif address == VTOR_ADDRESS:
            self._registers[address] = value & VTOR_WRITE_MASK
        self._trace("write", address, width, value, pc)

    def advance_time(self, ticks: int = 1) -> None:
        if ticks <= 0:
            raise ValueError("time must advance by a positive number of ticks")
        self.poll_state.elapsed_ticks += ticks
        if self._registers[RCC_CR] & HSE_ON:
            self.poll_state.hse_polls += ticks
            target = self.poll_state.hse_ready_after_polls
            if target is not None and self.poll_state.hse_polls >= target:
                if not self.poll_state.hse_ready:
                    self.poll_state.hse_ready = True
                    self.poll_state.cir_flags |= HSERDY_FLAG
        self._trace("advance_time", None, None, ticks, None)

    def wait_for_hse(self, *, max_polls: int, pc: int | None = None) -> None:
        if max_polls <= 0:
            raise ValueError("HSE poll bound must be positive")
        for _ in range(max_polls):
            if self.read(RCC_CR, pc=pc) & HSE_READY:
                return
            self.advance_time()
        if not self.read(RCC_CR, pc=pc) & HSE_READY:
            raise HSETimeout(max_polls, self.poll_state.elapsed_ticks)

    def wait_for_pll_ready(self, *, pc: int | None = None) -> None:
        raise UnboundedPollBlocker("RCC_CR.PLLRDY", PLL_READY, pc)

    def wait_for_sws(self, *, pc: int | None = None) -> None:
        raise UnboundedPollBlocker("RCC_CFGR.SWS", SWS_MASK, pc)
