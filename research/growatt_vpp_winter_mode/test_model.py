from research.growatt_vpp_winter_mode.model import Observation, WinterVppState, classify_transition


def test_zaba22_bridge_is_one_shot_and_clamped() -> None:
    state = WinterVppState(h30100=1, h3037=100)
    assert state.worker_step() == "vpp-tou"
    assert state.h30475 == 35
    assert state.bridge_latch
    state.h3037 = 10
    assert state.worker_step() == "vpp-tou"
    assert state.h30475 == 35


def test_pending_mask_blocks_zaba22_bridge() -> None:
    state = WinterVppState(h30100=1, h3037=20, pending_mask=1)
    assert state.worker_step() == "unresolved"
    assert state.h30475 == 0


def test_h30407_selects_remote_timer_only_inside_vpp() -> None:
    state = WinterVppState(h30100=1, h30407=1)
    assert state.worker_step() == "vpp-remote-timer"
    state.h30100 = 0
    assert state.worker_step() == "legacy"


def test_zaba23_observed_profile_does_not_promote_zaba22_bridge() -> None:
    state = WinterVppState(firmware_profile="zaba23-observed", h30100=1, h3037=10)
    assert state.worker_step() == "vpp-tou"
    assert state.h30475 == 0
    result = state.write("H30475", 20)
    assert not result.accepted
    assert result.exception_code == 1


def test_acknowledgement_and_public_readback_are_separate() -> None:
    state = WinterVppState()
    result = state.write("H30475", 10)
    assert result.accepted
    state.public_readback["H30475"] = 0
    assert state.read("H30475") == 0


def test_h192_is_preserved_without_invented_semantics() -> None:
    state = WinterVppState()
    assert state.write("H192", 64).accepted
    assert state.h192 == 64
    assert state.worker_step() == "legacy"


def test_evidence_class_is_not_upgraded_by_model() -> None:
    observation = Observation(
        "E-P2-005",
        "H192",
        "write",
        64,
        "experimental",
        "capture",
        "physical write",
        "high",
    )
    assert classify_transition(observation) == "experimental"
