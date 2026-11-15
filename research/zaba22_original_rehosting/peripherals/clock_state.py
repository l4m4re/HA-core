"""Evidence-bounded STM32F1 clock state transitions.

The register/status relationships in this module are hardware-defined.  The
firmware-derived wait bounds and the optional readiness delays are represented
separately, so a synthetic emulator policy cannot masquerade as silicon
behavior.  The exact ZABA22 derivative, PLL configuration, and SWS settling
semantics remain unresolved.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

RCC_CR = 0x40021000
RCC_CFGR = 0x40021004
RCC_CIR = 0x40021008

HSION = 1 << 0
HSIRDY = 1 << 1
HSEON = 1 << 16
HSERDY = 1 << 17
PLLON = 1 << 24
PLLRDY = 1 << 25
SW_MASK = 0b11
SWS_MASK = 0b11 << 2
HSERDYF = 1 << 3
PLLRDYF = 1 << 4

# CMSIS RCC_CIR.HSERDYC is bit 19.  It clears the HSE ready interrupt flag
# (bit 3); it does not disable HSE or directly alter HSERDY.
HSERDYC = 1 << 19
PLLRDYC = 1 << 20


class EvidenceClass(StrEnum):
    HARDWARE_DEFINED = "hardware-defined"
    FIRMWARE_DERIVED = "firmware-derived"
    SYNTHETIC_POLICY = "synthetic-policy"


class Oscillator(StrEnum):
    HSI = "hsi"
    HSE = "hse"
    PLL = "pll"


class OscillatorState(StrEnum):
    OFF = "off"
    STARTING = "starting"
    READY = "ready"


class SystemClockSource(StrEnum):
    HSI = "hsi"
    HSE = "hse"
    PLL = "pll"


class TransitionKind(StrEnum):
    RESET = "reset"
    ENABLE = "enable"
    DISABLE = "disable"
    REQUEST_SYSCLK = "request-sysclk"
    ADVANCE_TIME = "advance-time"
    READY = "ready"
    CLEAR_FLAG = "clear-flag"


class ClockStateError(RuntimeError):
    """Base class for a transition that cannot be justified or completed."""


class UnboundedPollBlocker(ClockStateError):
    """Firmware polls a readiness condition without a proven timeout."""

    def __init__(self, condition: str) -> None:
        self.condition = condition
        super().__init__(
            f"unbounded firmware poll for {condition}; "
            "exact derivative or explicit emulator policy is required"
        )


class BoundedPollTimeout(ClockStateError):
    """A firmware-derived bounded wait expired without hardware readiness."""

    def __init__(self, condition: str, max_polls: int) -> None:
        self.condition = condition
        self.max_polls = max_polls
        super().__init__(f"{condition} timeout after {max_polls} polls")


class InvalidClockTransition(ClockStateError):
    """The requested source is not ready or a clock invariant is violated."""


@dataclass(frozen=True)
class Transition:
    kind: TransitionKind
    subject: str
    evidence: EvidenceClass
    before: str
    after: str


@dataclass(frozen=True)
class ClockSnapshot:
    hsi: OscillatorState
    hse: OscillatorState
    pll: OscillatorState
    requested_sysclk: SystemClockSource
    sysclk: SystemClockSource
    hse_ready_flag: bool
    pll_ready_flag: bool


@dataclass(frozen=True)
class ReadResult:
    value: int
    evidence: EvidenceClass = EvidenceClass.HARDWARE_DEFINED


class ClockStateMachine:
    """A register-independent model of clock state and legal transitions."""

    def __init__(
        self,
        *,
        hse_ready_after_ticks: int | None = 0,
        pll_ready_after_ticks: int | None = None,
        sws_settle_after_ticks: int | None = None,
    ) -> None:
        for name, value in (
            ("hse_ready_after_ticks", hse_ready_after_ticks),
            ("pll_ready_after_ticks", pll_ready_after_ticks),
            ("sws_settle_after_ticks", sws_settle_after_ticks),
        ):
            if value is not None and value < 0:
                raise ValueError(f"{name} must not be negative")
        self._hse_delay = hse_ready_after_ticks
        self._pll_delay = pll_ready_after_ticks
        self._sws_delay = sws_settle_after_ticks
        self.transitions: list[Transition] = []
        self.reset()

    def reset(self) -> None:
        self.hsi = OscillatorState.READY
        self.hse = OscillatorState.OFF
        self.pll = OscillatorState.OFF
        self.requested_sysclk = SystemClockSource.HSI
        self.sysclk = SystemClockSource.HSI
        self._hse_ticks = 0
        self._pll_ticks = 0
        self._sws_ticks = 0
        self._hse_ready_flag = False
        self._pll_ready_flag = False
        self.transitions.append(
            Transition(
                TransitionKind.RESET,
                "clock",
                EvidenceClass.HARDWARE_DEFINED,
                "unknown",
                self.snapshot().sysclk.value,
            )
        )

    def snapshot(self) -> ClockSnapshot:
        return ClockSnapshot(
            self.hsi,
            self.hse,
            self.pll,
            self.requested_sysclk,
            self.sysclk,
            self._hse_ready_flag,
            self._pll_ready_flag,
        )

    def _transition(self, kind: TransitionKind, subject: str, before: str, after: str, evidence: EvidenceClass) -> None:
        self.transitions.append(Transition(kind, subject, evidence, before, after))

    def enable(self, oscillator: Oscillator) -> None:
        state = getattr(self, oscillator.value)
        if state is not OscillatorState.OFF:
            return
        setattr(self, oscillator.value, OscillatorState.STARTING)
        self._transition(TransitionKind.ENABLE, oscillator.value, state.value, "starting", EvidenceClass.HARDWARE_DEFINED)
        if oscillator is Oscillator.HSI:
            self.hsi = OscillatorState.READY
            self._transition(TransitionKind.READY, "hsi", "starting", "ready", EvidenceClass.HARDWARE_DEFINED)

    def disable(self, oscillator: Oscillator) -> None:
        state = getattr(self, oscillator.value)
        if state is OscillatorState.OFF:
            return
        setattr(self, oscillator.value, OscillatorState.OFF)
        if oscillator is Oscillator.HSE:
            self._hse_ticks = 0
            self._hse_ready_flag = False
        elif oscillator is Oscillator.PLL:
            self._pll_ticks = 0
            self._pll_ready_flag = False
        if self.sysclk is SystemClockSource(oscillator.value):
            self.sysclk = SystemClockSource.HSI
            self.requested_sysclk = SystemClockSource.HSI
        self._transition(TransitionKind.DISABLE, oscillator.value, state.value, "off", EvidenceClass.HARDWARE_DEFINED)

    def request_sysclk(self, source: SystemClockSource) -> None:
        if source is SystemClockSource.HSI and self.hsi is not OscillatorState.READY:
            raise InvalidClockTransition("HSI is not ready")
        if source is SystemClockSource.HSE and self.hse is not OscillatorState.READY:
            raise InvalidClockTransition("HSE is not ready")
        if source is SystemClockSource.PLL and self.pll is not OscillatorState.READY:
            raise InvalidClockTransition("PLL is not ready")
        before = self.requested_sysclk.value
        self.requested_sysclk = source
        self._sws_ticks = 0
        self._transition(TransitionKind.REQUEST_SYSCLK, "sw", before, source.value, EvidenceClass.HARDWARE_DEFINED)
        if self._sws_delay == 0:
            self.sysclk = source

    def advance_time(self, ticks: int = 1) -> None:
        if ticks <= 0:
            raise ValueError("time must advance by a positive number of ticks")
        before = self.snapshot().sysclk.value
        self._hse_ticks += ticks if self.hse is OscillatorState.STARTING else 0
        self._pll_ticks += ticks if self.pll is OscillatorState.STARTING else 0
        self._sws_ticks += ticks
        if self.hse is OscillatorState.STARTING and self._hse_delay is not None and self._hse_ticks >= self._hse_delay:
            self.hse = OscillatorState.READY
            self._hse_ready_flag = True
            self._transition(TransitionKind.READY, "hse", "starting", "ready", EvidenceClass.SYNTHETIC_POLICY)
        if self.pll is OscillatorState.STARTING and self._pll_delay is not None and self._pll_ticks >= self._pll_delay:
            self.pll = OscillatorState.READY
            self._pll_ready_flag = True
            self._transition(TransitionKind.READY, "pll", "starting", "ready", EvidenceClass.SYNTHETIC_POLICY)
        if self.requested_sysclk is not self.sysclk and self._sws_delay is not None and self._sws_ticks >= self._sws_delay:
            self.sysclk = self.requested_sysclk
            self._transition(TransitionKind.READY, "sws", before, self.sysclk.value, EvidenceClass.SYNTHETIC_POLICY)
        self._transition(TransitionKind.ADVANCE_TIME, "clock", before, self.snapshot().sysclk.value, EvidenceClass.SYNTHETIC_POLICY)

    def wait_for_hse(self, *, max_polls: int) -> None:
        if max_polls <= 0:
            raise ValueError("HSE poll bound must be positive")
        for _ in range(max_polls):
            if self.hse is OscillatorState.READY:
                return
            self.advance_time()
        if self.hse is not OscillatorState.READY:
            raise BoundedPollTimeout("RCC_CR.HSERDY", max_polls)

    def wait_for_pll_ready(self) -> None:
        if self.pll is not OscillatorState.READY:
            raise UnboundedPollBlocker("RCC_CR.PLLRDY")

    def wait_for_sws(self) -> None:
        if self.sysclk is not self.requested_sysclk:
            raise UnboundedPollBlocker("RCC_CFGR.SWS")

    def read_cr(self) -> ReadResult:
        value = HSION | HSIRDY
        if self.hse is not OscillatorState.OFF:
            value |= HSEON
        if self.hse is OscillatorState.READY:
            value |= HSERDY
        if self.pll is not OscillatorState.OFF:
            value |= PLLON
        if self.pll is OscillatorState.READY:
            value |= PLLRDY
        return ReadResult(value)

    def read_cfgr(self) -> ReadResult:
        source = {SystemClockSource.HSI: 0, SystemClockSource.HSE: 1, SystemClockSource.PLL: 2}[self.requested_sysclk]
        status = {SystemClockSource.HSI: 0, SystemClockSource.HSE: 1, SystemClockSource.PLL: 2}[self.sysclk]
        return ReadResult(source | status << 2)

    def read_cir(self) -> ReadResult:
        flags = (HSERDYF if self._hse_ready_flag else 0) | (PLLRDYF if self._pll_ready_flag else 0)
        return ReadResult(flags)

    def write_cir(self, value: int) -> None:
        if value & HSERDYC:
            self._hse_ready_flag = False
            self._transition(TransitionKind.CLEAR_FLAG, "HSERDYF", "set", "clear", EvidenceClass.HARDWARE_DEFINED)
        if value & PLLRDYC:
            self._pll_ready_flag = False
            self._transition(TransitionKind.CLEAR_FLAG, "PLLRDYF", "set", "clear", EvidenceClass.HARDWARE_DEFINED)
