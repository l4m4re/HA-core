"""State-transition tests for the evidence-bounded clock model."""

import pytest

from .peripherals.clock_state import (
    HSERDY,
    HSERDYC,
    HSERDYF,
    PLLRDY,
    PLLRDYC,
    PLLRDYF,
    ClockStateMachine,
    EvidenceClass,
    InvalidClockTransition,
    Oscillator,
    OscillatorState,
    SystemClockSource,
    UnboundedPollBlocker,
    BoundedPollTimeout,
)


def test_reset_is_hardware_defined_and_only_hsi_is_ready() -> None:
    clock = ClockStateMachine()

    assert clock.snapshot().hsi is OscillatorState.READY
    assert clock.snapshot().hse is OscillatorState.OFF
    assert clock.snapshot().pll is OscillatorState.OFF
    assert clock.read_cr().value & (HSERDY | PLLRDY) == 0
    assert clock.transitions[0].evidence is EvidenceClass.HARDWARE_DEFINED


def test_hse_ready_requires_enable_and_synthetic_elapsed_time() -> None:
    clock = ClockStateMachine(hse_ready_after_ticks=2)
    clock.enable(Oscillator.HSE)

    assert clock.snapshot().hse is OscillatorState.STARTING
    assert not clock.read_cr().value & HSERDY
    clock.advance_time()
    assert clock.snapshot().hse is OscillatorState.STARTING
    clock.advance_time()
    assert clock.snapshot().hse is OscillatorState.READY
    assert clock.read_cr().value & HSERDY
    assert any(event.evidence is EvidenceClass.SYNTHETIC_POLICY for event in clock.transitions)


def test_disabling_hse_clears_ready_and_falls_back_from_sysclk() -> None:
    clock = ClockStateMachine(hse_ready_after_ticks=0, sws_settle_after_ticks=0)
    clock.enable(Oscillator.HSE)
    clock.advance_time()
    clock.request_sysclk(SystemClockSource.HSE)
    assert clock.snapshot().sysclk is SystemClockSource.HSE

    clock.disable(Oscillator.HSE)

    assert clock.snapshot().hse is OscillatorState.OFF
    assert not clock.read_cr().value & HSERDY
    assert clock.snapshot().sysclk is SystemClockSource.HSI


def test_pll_and_sws_do_not_get_unconditional_ready_bits() -> None:
    clock = ClockStateMachine(pll_ready_after_ticks=None, sws_settle_after_ticks=None)
    clock.enable(Oscillator.PLL)

    assert not clock.read_cr().value & PLLRDY
    with pytest.raises(UnboundedPollBlocker, match="PLLRDY"):
        clock.wait_for_pll_ready()
    with pytest.raises(InvalidClockTransition, match="PLL is not ready"):
        clock.request_sysclk(SystemClockSource.PLL)
    assert not clock.read_cfgr().value & (0b11 << 2)


def test_hse_failure_is_firmware_derived_and_bounded() -> None:
    clock = ClockStateMachine(hse_ready_after_ticks=None)
    clock.enable(Oscillator.HSE)

    with pytest.raises(BoundedPollTimeout, match="3 polls"):
        clock.wait_for_hse(max_polls=3)

    assert all(
        event.evidence is not EvidenceClass.FIRMWARE_DERIVED
        for event in clock.transitions
        if event.kind.value == "advance-time"
    )
    assert EvidenceClass.FIRMWARE_DERIVED.value == "firmware-derived"


def test_hardware_cir_clear_bit_19_clears_hse_flag_only() -> None:
    clock = ClockStateMachine(hse_ready_after_ticks=0, pll_ready_after_ticks=0)
    clock.enable(Oscillator.HSE)
    clock.enable(Oscillator.PLL)
    clock.advance_time()

    assert clock.read_cir().value & (HSERDYF | PLLRDYF) == HSERDYF | PLLRDYF
    clock.write_cir(HSERDYC)

    assert not clock.read_cir().value & HSERDYF
    assert clock.read_cir().value & PLLRDYF
    assert clock.snapshot().hse is OscillatorState.READY


def test_pll_clear_bit_does_not_disable_pll_or_clear_ready_status() -> None:
    clock = ClockStateMachine(pll_ready_after_ticks=0)
    clock.enable(Oscillator.PLL)
    clock.advance_time()
    clock.write_cir(PLLRDYC)

    assert clock.snapshot().pll is OscillatorState.READY
    assert clock.read_cr().value & PLLRDY
    assert not clock.read_cir().value & PLLRDYF
