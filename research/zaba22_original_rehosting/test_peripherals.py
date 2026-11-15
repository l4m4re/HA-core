"""Contract tests for the P1-evidenced trace-driven peripheral model."""

import pytest

from .peripherals import HSETimeout, TraceDrivenPeripherals, UnboundedPollBlocker, UnsupportedMMIO
from .peripherals.model import (
    FLASH_ACR,
    RCC_CFGR,
    RCC_CFGR2,
    RCC_CR,
    RCC_CR_RESET,
    RCC_CIR,
    VTOR_ADDRESS,
    VTOR_WRITE_MASK,
)


def test_register_reset_values_and_valid_masked_writes() -> None:
    model = TraceDrivenPeripherals()

    assert model.read(RCC_CR) == RCC_CR_RESET
    model.write(RCC_CR, 0xFFFFFFFF)
    model.write(RCC_CFGR, 0xFFFFFFFF)
    model.write(RCC_CIR, 0xFFFFFFFF)
    model.write(RCC_CFGR2, 0xFFFFFFFF)
    model.write(FLASH_ACR, 0xFFFFFFFF)

    assert model.read(RCC_CR) & (1 << 1 | 1 << 17 | 1 << 25) == 1 << 1
    assert model.read(RCC_CFGR) & (0b11 << 2) == 0
    assert model.read(RCC_CIR) & 0xFFFF0000 == 0
    assert model.read(FLASH_ACR) & (1 << 5) == 1 << 5


def test_vtor_write_applies_alignment_mask() -> None:
    model = TraceDrivenPeripherals()

    model.write(VTOR_ADDRESS, 0x200001FF)

    assert model.read(VTOR_ADDRESS) == 0x200001FF & VTOR_WRITE_MASK


def test_ready_transition_is_separate_from_register_write_and_time() -> None:
    model = TraceDrivenPeripherals(hse_ready_after_polls=2)
    model.write(RCC_CR, 1 << 16)

    assert not model.read(RCC_CR) & (1 << 17)
    model.advance_time()
    assert not model.read(RCC_CR) & (1 << 17)
    model.advance_time()
    assert model.read(RCC_CR) & (1 << 17)
    assert model.poll_state.elapsed_ticks == 2


def test_cir_ready_flag_is_cleared_by_its_documented_write_one_clear_bit() -> None:
    model = TraceDrivenPeripherals(hse_ready_after_polls=1)
    model.write(RCC_CR, 1 << 16)
    model.advance_time()

    assert model.read(RCC_CIR) & (1 << 3)
    model.write(RCC_CIR, 1 << 18)
    assert not model.read(RCC_CIR) & (1 << 3)


def test_hse_wait_has_an_explicit_bounded_timeout() -> None:
    model = TraceDrivenPeripherals(hse_ready_after_polls=None)
    model.write(RCC_CR, 1 << 16)

    with pytest.raises(HSETimeout, match="3 polls"):
        model.wait_for_hse(max_polls=3, pc=0x080020BC)


def test_pll_and_sws_waits_remain_unbounded_poll_blockers() -> None:
    model = TraceDrivenPeripherals()

    with pytest.raises(UnboundedPollBlocker, match="PLLRDY"):
        model.wait_for_pll_ready(pc=0x080020D0)
    with pytest.raises(UnboundedPollBlocker, match="SWS"):
        model.wait_for_sws(pc=0x080020E0)


@pytest.mark.parametrize("address,width", ((0x40021030, 4), (RCC_CR, 2), (RCC_CR + 1, 4)))
def test_invalid_width_and_address_are_typed_mmio_blockers(address: int, width: int) -> None:
    with pytest.raises(UnsupportedMMIO) as error:
        TraceDrivenPeripherals().read(address, width=width, pc=0x080020BC)

    assert error.value.address == address
    assert error.value.width == width
    assert error.value.pc == 0x080020BC
