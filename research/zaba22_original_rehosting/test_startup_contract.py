"""Executable tests for the original ZABA22 startup contract."""

from pathlib import Path

import pytest

from .emulator.startup_contract import (
    EXPECTED_INITIAL_SP,
    EXPECTED_RESET_PC,
    EXPECTED_RESET_RAW,
    FLASH_BASE,
    FLASH_REGION,
    RAM_REGION,
    RCC_ADDRESS,
    RESET_PROBE_PC,
    ContractError,
    EmulatorStartupState,
    FirmwareStartupState,
    LoaderContract,
    StateOrigin,
    collect_startup_evidence,
    emulator_startup_state,
    firmware_startup_state,
)
from .harness import load_payload


def test_vector_state_is_original_and_thumb() -> None:
    state = firmware_startup_state(load_payload())

    assert state == FirmwareStartupState(
        EXPECTED_INITIAL_SP,
        EXPECTED_RESET_RAW,
        EXPECTED_RESET_PC,
        True,
    )
    assert state.origin is StateOrigin.FIRMWARE_VECTOR


def test_loader_contract_places_image_and_vtor_without_claiming_peripheral_fidelity() -> None:
    contract = LoaderContract(Path("ZABA22-payload.bin"))

    contract.validate()
    assert contract.qemu_arguments() == (
        "-device",
        "loader,file=ZABA22-payload.bin,addr=0x8000000",
        "-device",
        "loader,addr=0xe000ed08,data=0x8000000,data-len=4",
    )
    assert FLASH_REGION.contains(FLASH_BASE, 0x40000)
    assert RAM_REGION.contains(EXPECTED_INITIAL_SP, 4)


def test_firmware_and_emulator_state_have_distinct_provenance() -> None:
    firmware = firmware_startup_state(load_payload())
    emulator = emulator_startup_state(
        initial_sp=firmware.initial_sp,
        reset_pc=firmware.reset_pc,
        thumb=firmware.thumb,
    )

    assert firmware.origin is StateOrigin.FIRMWARE_VECTOR
    assert emulator.origin is StateOrigin.EMULATOR_PROVIDED
    assert not isinstance(emulator, FirmwareStartupState)
    assert emulator.vtor == FLASH_BASE


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        (b"short", "shorter than"),
        ((EXPECTED_INITIAL_SP).to_bytes(4, "little") + b"\x00\x00\x00\x08", "Thumb"),
    ),
)
def test_invalid_vector_state_fails_at_boundary(payload: bytes, message: str) -> None:
    with pytest.raises(ContractError, match=message):
        firmware_startup_state(payload)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"initial_sp": 0x1000, "reset_pc": EXPECTED_RESET_PC, "thumb": True}, "SP"),
        ({"initial_sp": EXPECTED_INITIAL_SP, "reset_pc": EXPECTED_RESET_PC, "thumb": False}, "Thumb"),
        ({"initial_sp": EXPECTED_INITIAL_SP, "reset_pc": EXPECTED_RESET_PC + 1, "thumb": True}, "PC"),
        ({"initial_sp": EXPECTED_INITIAL_SP, "reset_pc": EXPECTED_RESET_PC, "thumb": True, "vtor": 0}, "VTOR"),
    ),
)
def test_invalid_emulator_state_fails_at_boundary(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ContractError, match=message):
        emulator_startup_state(**kwargs)


@pytest.mark.parametrize(
    ("contract", "message"),
    (
        (LoaderContract(Path("image.bin"), flash_base=0), "flash base"),
        (LoaderContract(Path("image.bin"), vtor_value=0), "VTOR"),
        (LoaderContract(Path("image.bin")), "size"),
    ),
)
def test_invalid_loader_contract_fails_at_boundary(
    contract: LoaderContract, message: str
) -> None:
    image_size = 1 if message == "size" else 0x40000

    with pytest.raises(ContractError, match=message):
        contract.validate(image_size=image_size)


def test_bounded_reset_evidence_stops_at_known_original_mmio_boundary() -> None:
    evidence = collect_startup_evidence(max_instructions=200)

    assert evidence["bounded"] is True
    assert evidence["stop_reason"] == "mmio_blocker"
    assert evidence["stop_pc"] == RESET_PROBE_PC
    assert evidence["mmio_events"][0]["address"] == RCC_ADDRESS


def test_non_positive_probe_bound_is_invalid() -> None:
    with pytest.raises(ContractError, match="bound"):
        collect_startup_evidence(max_instructions=0)
