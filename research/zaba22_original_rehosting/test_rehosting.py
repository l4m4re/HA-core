from __future__ import annotations

import hashlib

from .harness import (
    BYTE_SUM_FUNCTION,
    CRC16_FUNCTION,
    EXPECTED_PAYLOAD_SHA256,
    execute_original,
    execute_reset_probe,
    load_payload,
)


def test_original_payload_hash_and_vector() -> None:
    payload = load_payload()
    assert hashlib.sha256(payload).hexdigest() == EXPECTED_PAYLOAD_SHA256
    assert int.from_bytes(payload[0:4], "little") == 0x20000CF8
    assert int.from_bytes(payload[4:8], "little") == 0x08003511


def test_original_crc16_function_reproduces_modbus_vectors() -> None:
    vectors = ((b"", 0xFFFF), (bytes.fromhex("010300000002"), 0x0BC4), (bytes.fromhex("010300000002c40b"), 0))
    for data, expected in vectors:
        result = execute_original(CRC16_FUNCTION, data, seed_crc_tables=True)
        assert result.original_bytes
        assert result.stop_reason == "return_stub"
        assert result.error is None
        assert result.output == expected
        assert not result.mmio_events


def test_original_byte_sum_function_has_independent_oracle() -> None:
    data = b"ZABA22-original"
    result = execute_original(BYTE_SUM_FUNCTION, data)
    assert result.original_bytes
    assert result.stop_reason == "return_stub"
    assert result.output == sum(data)
    assert result.trace_digest


def test_reset_probe_records_exact_first_mmio_blocker() -> None:
    result = execute_reset_probe()
    assert result.stop_reason == "mmio_blocker"
    assert result.mmio_events
    assert result.mmio_events[0]["address"] == 0x40021000
    assert result.trace[-1][0] == 0x080020BC


def test_trace_contains_original_entry_and_return_stub() -> None:
    result = execute_original(BYTE_SUM_FUNCTION, b"abc")
    addresses = [address for address, _size in result.trace]
    assert addresses[0] == BYTE_SUM_FUNCTION
    assert addresses[-1] == 0x20008000
