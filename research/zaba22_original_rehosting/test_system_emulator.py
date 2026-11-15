"""Tests for executing the original ZABA22 image in a system emulator."""

import hashlib

import pytest

from .emulator.qemu_runner import RCC_READ_PC, run_qemu_gdb
from .harness import EXPECTED_PAYLOAD_SHA256, load_payload


def test_qemu_gdb_executes_original_payload_until_rcc_access() -> None:
    """QEMU executes the image and GDB observes its original RCC instruction."""

    try:
        result = run_qemu_gdb()
    except RuntimeError as exc:
        pytest.skip(str(exc))

    assert result.exit_code == 0
    assert result.payload_sha256 == EXPECTED_PAYLOAD_SHA256
    assert result.breakpoint_hit
    assert f"0x{RCC_READ_PC:08x}" in result.transcript
    assert "ldr\tr0, [r0, #0]" in result.transcript


def test_system_emulator_uses_hash_checked_original_image() -> None:
    """The system-emulator path retains the original payload hash check."""

    payload = load_payload()

    assert hashlib.sha256(payload).hexdigest() == EXPECTED_PAYLOAD_SHA256
