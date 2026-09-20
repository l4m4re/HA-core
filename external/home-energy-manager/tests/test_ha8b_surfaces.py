"""HA-8B typed feedback, provider, and compatibility contract tests."""

from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace

from custom_components.growatt_local.API.const import DeviceTypes
from custom_components.growatt_local.API.device_type.base import (
    ATTR_BATTERY_CURRENT,
    ATTR_BMS_BATTERY_CURRENT,
    ATTR_CURRENT_PRIORITY,
    ATTR_LOAD_FIRST_STOP_SOC,
)
from custom_components.growatt_local.API.device_type.storage_120 import (
    XH_TOU_SETTING_KEYS,
)
from custom_components.growatt_local.API.growatt import get_register_information
from custom_components.growatt_local.API.utils import process_registers
from custom_components.growatt_local.sensor import (
    GrowattDeviceEntity,
    GrowattPriorityEntity,
    GrowattScheduleEntity,
    GrowattTouSettingsEntity,
)
from custom_components.growatt_local.sensor_types.inverter import INVERTER_SENSOR_TYPES
from custom_components.growatt_local.sensor_types.storage import STORAGE_SENSOR_TYPES
from ems_contract.controls import GROWATT_XH_CONTROLS, ActuatorClass
from ems_contract.growatt import PriorityMode, decode_priority_word, decode_xh_schedule
from ems_contract.providers import (
    EvAvailability,
    EvProviderState,
    PriceBasis,
    PriceInterval,
    PriceProviderState,
)
from ems_contract.snapshot import EmsSnapshot, GrowattState


def test_priority_values_and_unknown_raw_value_are_preserved() -> None:
    """I3144 has typed known modes and observable unknown values."""

    assert decode_priority_word(0).mode is PriorityMode.LOAD_FIRST
    assert decode_priority_word(1).mode is PriorityMode.BATTERY_FIRST
    assert decode_priority_word(2).mode is PriorityMode.GRID_FIRST
    unknown = decode_priority_word(7)
    assert unknown.mode is None
    assert unknown.raw == 7
    assert unknown.state == "unknown_7"


def test_xh_schedule_decodes_ha7b_live_words() -> None:
    """HA-7B Time 1-3 and zero slots retain their documented semantics."""

    raw = {
        3038: 0x3700,
        3039: 0x173B,
        3040: 0xA000,
        3041: 0x0700,
        3042: 0x2000,
        3043: 0x043B,
        3044: 0,
        3045: 0,
        3050: 0,
        3051: 0,
        3052: 0,
        3053: 0,
        3054: 0,
        3055: 0,
        3056: 0,
        3057: 0,
        3058: 0,
        3059: 0,
    }

    schedule = decode_xh_schedule(raw)

    assert (schedule[0].start.isoformat(), schedule[0].end.isoformat()) == (
        "23:00:00",
        "23:59:00",
    )
    assert schedule[0].priority.mode is PriorityMode.BATTERY_FIRST
    assert not schedule[0].enabled
    assert (schedule[1].start.isoformat(), schedule[1].end.isoformat()) == (
        "00:00:00",
        "07:00:00",
    )
    assert schedule[1].priority.mode is PriorityMode.BATTERY_FIRST
    assert schedule[1].enabled
    assert schedule[2].end.isoformat() == "04:59:00"
    assert not schedule[2].enabled
    assert all(not slot.enabled for slot in schedule[3:])
    assert all(slot.valid for slot in schedule)


def test_xh_schedule_retains_raw_words_and_unknown_priority() -> None:
    """Reserved priority values remain visible in structured attributes."""

    raw = dict.fromkeys((*range(3038, 3046), *range(3050, 3060)), 0)
    raw[3038] = 0xE001
    raw[3039] = 0x0102

    slot = decode_xh_schedule(raw)[0]

    assert slot.raw_start_word == 0xE001
    assert slot.raw_end_word == 0x0102
    assert slot.priority.raw == 3
    assert slot.priority.mode is None
    assert not slot.valid


def test_priority_and_schedule_are_mapped_without_changing_battery_currents() -> None:
    """The new feedback surface preserves I3170/I3217 as distinct quantities."""

    registers = get_register_information(DeviceTypes.HYBRID_120_TL_XH)
    assert registers.input[3144].name == ATTR_CURRENT_PRIORITY
    assert registers.input[3170].name == ATTR_BATTERY_CURRENT
    assert registers.input[3170].signed is False
    assert registers.input[3217].name == ATTR_BMS_BATTERY_CURRENT
    assert registers.input[3217].signed is True
    assert registers.holding[3049].name == "ac_charge_enabled"
    assert registers.input[3049].name == "output_energy_today"
    assert (
        process_registers({3144: registers.input[3144]}, {3144: 7})[
            ATTR_CURRENT_PRIORITY
        ].state
        == "unknown_7"
    )


def test_feedback_entities_have_additive_stable_unique_ids() -> None:
    """New feedback entities do not reuse an existing public ID."""

    entry = SimpleNamespace(
        data={
            "serial_number": "SNL0CGV020",
            "model": "MIN 6000TL-XH",
            "firmware": "fixture",
        },
        options={"name": "Growatt"},
    )
    coordinator = SimpleNamespace(data={})

    priority = GrowattPriorityEntity(coordinator, entry)
    schedule = GrowattScheduleEntity(coordinator, entry)

    assert priority.unique_id == "growatt_local_SNL0CGV020_current_priority"
    assert schedule.unique_id == "growatt_local_SNL0CGV020_xh_schedule"
    assert schedule.coordinator_context == "xh_schedule_1_start"
    tou = GrowattTouSettingsEntity(coordinator, entry)
    assert tou.unique_id == "growatt_local_SNL0CGV020_xh_tou_settings"
    assert tou.coordinator_context == XH_TOU_SETTING_KEYS[0]

    registers = get_register_information(DeviceTypes.HYBRID_120_TL_XH)
    assert registers.holding[3082].name == ATTR_LOAD_FIRST_STOP_SOC


def test_production_sensor_contract_fixture() -> None:
    """Production Energy-dashboard semantics remain a deliberate fixture."""

    fixture_path = (
        Path(__file__).parent / "fixtures" / "production_sensor_contract.json"
    )
    fixture = json.loads(fixture_path.read_text())
    descriptions = {
        description.key: description
        for description in INVERTER_SENSOR_TYPES + STORAGE_SENSOR_TYPES
    }
    registers = get_register_information(DeviceTypes.HYBRID_120_TL_XH)
    entry = SimpleNamespace(
        data={
            "serial_number": "SNL0CGV020",
            "model": "MIN 6000TL-XH",
            "firmware": "fixture",
        },
        options={"name": "Growatt"},
    )

    for expected in fixture.values():
        description = descriptions[expected["key"]]
        register = registers.input[expected["source_register"]]
        entity = GrowattDeviceEntity(SimpleNamespace(data={}), description, entry)
        assert entity.unique_id == expected["unique_id"]
        assert description.device_class.value == expected["device_class"]
        assert description.state_class.value == expected["state_class"]
        assert description.native_unit_of_measurement == expected["unit"]
        assert register.name == expected["key"]
        assert description.midnight_reset is (expected["counter"] == "daily_reset")


def test_persistent_growatt_controls_require_noop_and_readback_policy() -> None:
    """Writable Modbus metadata does not make schedule controls fast runtime."""

    controls = {control.control_id: control for control in GROWATT_XH_CONTROLS}
    for control_id in (
        "inverter_power_control",
        "grid_first_discharge_rate",
        "grid_first_stop_soc",
        "xh_schedule",
        "battery_first_charge_rate",
        "battery_first_stop_soc",
        "ac_charge_enabled",
        "load_first_stop_soc",
    ):
        control = controls[control_id]
        assert control.actuator_class is ActuatorClass.PERSISTENT_OR_UNKNOWN
        assert control.write_on_change_required
        assert control.verify_readback_required
        assert control.minimum_cadence_ms is None


def test_provider_contracts_preserve_price_semantics_and_missing_ev_data() -> None:
    """Price basis and unavailable EV fields remain explicit."""

    now = datetime.now(UTC)
    interval = PriceInterval(
        start=now,
        end=now,
        import_price=Decimal("0.31"),
        export_price=Decimal("0.08"),
        source="fixture",
        retrieved_at=now,
        valid=True,
        price_basis=PriceBasis.ALL_IN_IMPORT,
    )
    price = PriceProviderState(
        current=interval,
        future=(interval,),
        retrieved_at=now,
        valid=True,
    )
    ev = EvProviderState(
        availability=EvAvailability.NOT_CONFIGURED,
        observed_at=None,
        valid=False,
    )
    snapshot = EmsSnapshot(
        timestamp=now,
        growatt=GrowattState(observed_at=now, telemetry_valid=True),
        price=price,
        ev=ev,
    )

    assert snapshot.price.current.price_basis is PriceBasis.ALL_IN_IMPORT
    assert snapshot.ev.availability is EvAvailability.NOT_CONFIGURED
    assert snapshot.ev.soc_pct is None

    stale = PriceProviderState(
        current=None,
        future=(),
        retrieved_at=now,
        valid=False,
        error_reason="stale",
    )
    partial_ev = EvProviderState(
        availability=EvAvailability.AVAILABLE,
        observed_at=now,
        connected=True,
        charging=False,
        valid=True,
        error_reason="soc_unavailable",
    )
    assert not stale.valid
    assert stale.error_reason == "stale"
    assert partial_ev.connected is True
    assert partial_ev.soc_pct is None
