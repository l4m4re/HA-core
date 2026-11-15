"""Tests proving original reset execution reaches and passes the RCC read."""

from .emulator.peripheral_execution import execute_reset_with_peripherals


def test_original_reset_completes_rcc_read_before_next_blocker() -> None:
    result = execute_reset_with_peripherals()

    assert result.payload_sha256 == "97c22678f14e490a748df03ea1c9d2940a74a1dd239d45e290a0843dab90c858"
    assert result.stop_reason == "peripheral_blocker"
    assert result.trace[-1][0] != 0x080020BC
    assert any(event["address"] == 0x40021000 and event["operation"] == "read" for event in result.peripheral_events)
    assert result.blocker is not None and "unbounded poll" in result.blocker


def test_original_reset_with_no_hse_transition_is_bounded() -> None:
    result = execute_reset_with_peripherals(hse_ready_after_polls=None, max_instructions=500)

    assert result.stop_reason == "instruction_limit"
    assert result.blocker is None
