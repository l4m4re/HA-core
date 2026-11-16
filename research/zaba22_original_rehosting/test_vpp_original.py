from __future__ import annotations

import pytest

from .vpp.original_vpp import (
    BRIDGE_STOP,
    H30475,
    execute_bridge,
    execute_fc06_pending_gate,
)


@pytest.mark.parametrize(
    ("pending_mask", "expected_exception", "expected_stop"),
    (
        (0, False, "emulator_error"),
        (1, True, "pending_response_stop"),
        (0x2000, True, "pending_response_stop"),
    ),
    ids=("clear-reaches-dispatch", "one-bit-blocks", "bit13-blocks"),
)
def test_original_fc06_pending_gate(
    pending_mask: int, expected_exception: bool, expected_stop: str
) -> None:
    result = execute_fc06_pending_gate(pending_mask=pending_mask)

    assert result.stop_reason == expected_stop
    if expected_exception:
        assert result.error is None
        assert result.response[1:3] == bytes((0x86, 0x01))
    else:
        assert result.error is not None
        assert result.response[1:3] == b"\x00\x00"


@pytest.mark.parametrize(
    ("h30100", "h3037", "latch", "expected_h30475"),
    (
        (0, 10, 0, 0),
        (1, 10, 0, 10),
        (1, 35, 0, 35),
        (1, 36, 0, 35),
        (1, 100, 0, 35),
        (1, 20, 1, 0),
    ),
    ids=("legacy", "bridge-10", "bridge-35", "clamp-36", "clamp-100", "latch-set"),
)
def test_original_h3037_bridge(
    h30100: int, h3037: int, latch: int, expected_h30475: int
) -> None:
    result = execute_bridge(h30100=h30100, h3037=h3037, latch=latch)

    assert result.error is None
    assert result.stop_reason == "natural_bridge_stop"
    assert result.stop_pc == BRIDGE_STOP
    stores = [write for write in result.writes if write.address == H30475]
    observed = stores[-1].value if stores else 0
    assert observed == expected_h30475
    latch_stores = [write for write in result.writes if write.address == 0x2000E6EB]
    if expected_h30475:
        assert latch_stores
        assert latch_stores[-1].value & 1
        assert any(write.address == 0x2000EB60 for write in result.writes)
    else:
        assert not latch_stores
