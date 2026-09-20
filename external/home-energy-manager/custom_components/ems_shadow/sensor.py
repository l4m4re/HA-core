"""Read-only live EMS planning entities for DEV staging."""

from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from functools import partial
import logging
import math
from typing import Any, cast
from zoneinfo import ZoneInfo

from custom_components.ems_contract.planner import PlannerConfig, plan_shadow_ems
from custom_components.ems_contract.price_trends import (
    PriceObservation,
    calculate_price_trends,
)
from custom_components.ems_contract.providers import (
    EvAvailability,
    EvProviderState,
    PriceInterval,
    PriceProviderState,
)
from custom_components.ems_contract.snapshot import EmsSnapshot, GrowattState
from custom_components.ems_contract.zoe_prediction import (
    ZoeRateEstimate,
    load_replay_rate_model,
    plan_price_aware_charge,
    project_charge_session,
)
from custom_components.ems_contract.zonneplan import parse_zonneplan_entity

from homeassistant.components.recorder import get_instance, history
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import dt as dt_util

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = cv.PLATFORM_SCHEMA.extend({})
# Keep the DEV preflight fresher than Peblar's 60-second limit.
SCAN_INTERVAL = timedelta(seconds=30)
PRICE_ENTITY = "sensor.zonneplan_current_quarter_hourly_electricity_tariff"
GROWATT_SOC_ENTITY = "sensor.growatt_soc"
GROWATT_AC_CHARGE_ENTITY = "switch.growatt_ac_charge"
GROWATT_POWER_CONTROL_ENTITY = "switch.growatt_power_control"
PEBLAR_POWER_ENTITY = "sensor.peblar_ev_charger_power"
PEBLAR_STATE_ENTITY = "sensor.peblar_ev_charger_state"
PEBLAR_LIMIT_ENTITY = "number.peblar_ev_charger_charge_limit"
PEBLAR_CHARGE_ENABLE_ENTITY = "switch.peblar_ev_charger_charge"
PEBLAR_MODE_ENTITY = "select.peblar_ev_charger_smart_charging"
LIVE_ZOE_SOC_ENTITIES = (
    "sensor.zoe_soc",
    "sensor.zoe_battery_soc",
    "sensor.zoe_state_of_charge",
    "sensor.canze_zoe_soc",
    "sensor.renault_zoe_battery_level",
)
_UNKNOWN = {"", "unknown", "unavailable", "none"}
PEBLAR_MAX_AGE = timedelta(seconds=60)
# Peblar's user-configuration coordinator polls this select every five minutes.
PEBLAR_MODE_MAX_AGE = timedelta(minutes=6)
# A state can be reported just after this coordinator captures its clock.
MAX_FUTURE_REPORT_SKEW = timedelta(seconds=5)
ZOE_MAX_AGE = timedelta(minutes=5)


def _numeric_state(state: State | None) -> float | None:
    if state is None or state.state.lower() in _UNKNOWN:
        return None
    try:
        value = float(state.state)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _state_health(
    state: State | None, *, now: datetime, maximum_age: timedelta
) -> dict[str, object]:
    if state is None:
        return {"status": "not_configured", "reason": "entity_missing"}
    if state.state.lower() in _UNKNOWN:
        return {"status": "unavailable", "reason": f"state_{state.state.lower()}"}
    observed_at = state.last_reported or state.last_updated
    age = now - observed_at
    if age < -MAX_FUTURE_REPORT_SKEW:
        return {
            "status": "unavailable",
            "reason": "timestamp_in_future",
            "last_reported": observed_at.isoformat(),
        }
    age_seconds = max(0.0, age.total_seconds())
    result: dict[str, object] = {
        "status": "stale" if age_seconds > maximum_age.total_seconds() else "available",
        "age_seconds": round(age_seconds, 1),
        "last_reported": observed_at.isoformat(),
    }
    if age_seconds > maximum_age.total_seconds():
        result["reason"] = "state_stale"
    return result


def _price_interval(item: PriceInterval) -> dict[str, object]:
    return {
        "start": item.start.isoformat(),
        "end": item.end.isoformat(),
        "import_price_eur_per_kwh": (
            str(item.import_price) if item.import_price is not None else None
        ),
        "tax_excluded_price_eur_per_kwh": (
            str(item.tax_excluded_price)
            if item.tax_excluded_price is not None
            else None
        ),
        "price_basis": item.price_basis.value,
    }


class EmsShadowCoordinator(DataUpdateCoordinator[dict[str, object]]):
    """Combine current HA states without registering any control services."""

    def __init__(
        self,
        hass: HomeAssistant,
        rate_model: tuple[ZoeRateEstimate, ...],
    ) -> None:
        """Set up the read-only shared input coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.hass = hass
        self.rate_model = rate_model

    async def _async_price_history(self, now: datetime) -> tuple[PriceObservation, ...]:
        result = await get_instance(self.hass).async_add_executor_job(
            partial(
                history.get_significant_states,
                self.hass,
                now - timedelta(hours=24),
                now,
                [PRICE_ENTITY],
                significant_changes_only=False,
                no_attributes=True,
            )
        )
        observations: list[PriceObservation] = []
        for item in result.get(PRICE_ENTITY, []):
            if not isinstance(item, State):
                continue
            value = _numeric_state(item)
            if value is None or item.last_updated is None:
                continue
            observations.append(
                PriceObservation(item.last_updated, Decimal(str(value)))
            )
        return tuple(observations)

    async def _async_update_data(self) -> dict[str, object]:
        now = dt_util.now()
        planner_config = PlannerConfig()
        growatt_state = self.hass.states.get(GROWATT_SOC_ENTITY)
        battery_soc = _numeric_state(growatt_state)
        growatt_health = _state_health(
            growatt_state,
            now=now,
            maximum_age=planner_config.minimum_telemetry_freshness,
        )
        growatt_ac_charge_state = self.hass.states.get(GROWATT_AC_CHARGE_ENTITY)
        growatt_ac_charge_health = _state_health(
            growatt_ac_charge_state,
            now=now,
            maximum_age=planner_config.minimum_telemetry_freshness,
        )
        growatt_power_control_state = self.hass.states.get(GROWATT_POWER_CONTROL_ENTITY)
        growatt_power_control_health = _state_health(
            growatt_power_control_state,
            now=now,
            maximum_age=planner_config.minimum_telemetry_freshness,
        )
        if battery_soc is not None and not 0 <= battery_soc <= 100:
            growatt_health = {
                **growatt_health,
                "status": "unavailable",
                "reason": "soc_out_of_range",
            }
        growatt_observed = (
            growatt_state.last_reported or growatt_state.last_updated
            if growatt_state
            else None
        )
        if growatt_health["status"] != "available":
            battery_soc = None

        price_state = self.hass.states.get(PRICE_ENTITY)
        price_health = _state_health(
            price_state,
            now=now,
            maximum_age=planner_config.minimum_price_data_freshness,
        )
        price_retrieved_at = (
            price_state.last_reported or price_state.last_updated
            if price_state
            else None
        )
        if price_state is None or price_health["status"] != "available":
            prices = PriceProviderState(
                current=None,
                future=(),
                retrieved_at=price_retrieved_at,
                valid=False,
                error_reason=str(price_health.get("reason", "price_unavailable")),
            )
        else:
            prices = parse_zonneplan_entity(
                {"state": price_state.state, "attributes": price_state.attributes},
                now=now,
                retrieved_at=price_retrieved_at,
            )

        histories = await self._async_price_history(now)
        trends = calculate_price_trends(histories, now=now)
        growatt = GrowattState(
            observed_at=growatt_observed,
            battery_soc_pct=battery_soc,
            telemetry_valid=battery_soc is not None,
        )
        zoe_candidates = [
            (entity_id, self.hass.states.get(entity_id))
            for entity_id in LIVE_ZOE_SOC_ENTITIES
            if self.hass.states.get(entity_id) is not None
        ]
        zoe_recent_candidate = max(
            zoe_candidates,
            key=lambda candidate: candidate[1].last_reported,
            default=None,
        )
        zoe_fresh_candidates = [
            (entity_id, state)
            for entity_id, state in zoe_candidates
            if state is not None
            and _numeric_state(state) is not None
            and _state_health(state, now=now, maximum_age=ZOE_MAX_AGE)["status"]
            == "available"
        ]
        zoe_state = max(
            zoe_fresh_candidates,
            key=lambda candidate: candidate[1].last_reported,
            default=None,
        )
        zoe_entity_id = (
            zoe_state[0]
            if zoe_state
            else zoe_recent_candidate[0]
            if zoe_recent_candidate
            else None
        )
        zoe_state = zoe_state[1] if zoe_state else None
        live_zoe_soc = _numeric_state(zoe_state)
        if live_zoe_soc is not None and not 0 <= live_zoe_soc <= 100:
            live_zoe_soc = None
        zoe_health = (
            _state_health(zoe_state, now=now, maximum_age=ZOE_MAX_AGE)
            if zoe_state
            else _state_health(
                zoe_recent_candidate[1] if zoe_recent_candidate else None,
                now=now,
                maximum_age=ZOE_MAX_AGE,
            )
        )
        if zoe_state is None and zoe_recent_candidate:
            zoe_state = zoe_recent_candidate[1]
        if (
            zoe_candidates
            and live_zoe_soc is None
            and zoe_health["status"] == "available"
        ):
            zoe_health = {"status": "unavailable", "reason": "soc_invalid"}
        ev = EvProviderState(
            availability=(
                EvAvailability.AVAILABLE
                if live_zoe_soc is not None
                else EvAvailability.UNAVAILABLE
                if zoe_candidates
                else EvAvailability.NOT_CONFIGURED
            ),
            observed_at=(
                (zoe_state.last_reported or zoe_state.last_updated)
                if zoe_state
                else None
            ),
            soc_pct=live_zoe_soc,
            valid=live_zoe_soc is not None,
            error_reason=(
                None
                if live_zoe_soc is not None
                else str(
                    zoe_health.get("reason", "vehicle_soc_provider_not_configured")
                )
            ),
        )
        snapshot = EmsSnapshot(
            timestamp=now,
            growatt=growatt,
            price=prices,
            ev=ev,
        )
        battery_plan = plan_shadow_ems(snapshot, planner_config, price=prices)
        battery_plan_data = battery_plan.as_dict()
        for key in (
            "price_intervals_considered",
            "desired_slots",
            "schedule_diff",
            "write_budget",
            "hypothetical_write_count",
            "skipped_no_change_count",
            "actual_schedule",
        ):
            battery_plan_data.pop(key, None)
        battery_plan_data["operation"] = "shadow_only"
        battery_plan_data["automatic_dispatch"] = False
        battery_plan_data["decision"] = (
            "no_charge_needed"
            if battery_plan.valid and battery_plan.required_energy_kwh == 0
            else battery_plan.mode.value
        )
        battery_plan_data["assumptions"] = {
            "battery_usable_capacity_kwh": str(
                planner_config.battery_usable_capacity_kwh
            ),
            "capacity_basis": "provisional_generic_default_not_device_verified",
            "maximum_ac_battery_charge_power_w": str(
                planner_config.maximum_ac_battery_charge_power_w
            ),
            "charging_efficiency": str(planner_config.charging_efficiency),
            "efficiency_basis": "provisional_generic_default_not_device_verified",
            "battery_wear_cost_eur_per_kwh_stored": str(
                planner_config.battery_wear_cost_eur_per_kwh_stored
            ),
            "battery_wear_basis": planner_config.battery_wear_assumption,
        }

        now_local = now.astimezone(ZoneInfo(planner_config.timezone))
        departure = now_local.replace(hour=7, minute=0, second=0, microsecond=0)
        if departure <= now_local:
            departure += timedelta(days=1)
        live_limit_state = self.hass.states.get(PEBLAR_LIMIT_ENTITY)
        live_limit = _numeric_state(live_limit_state)
        live_limit_health = _state_health(
            live_limit_state, now=now, maximum_age=PEBLAR_MAX_AGE
        )
        supported_settings = {
            estimate.current_setting_a
            for estimate in self.rate_model
            if estimate.band == "all"
        }
        if live_zoe_soc is not None:
            current_setting_a = (
                round(live_limit)
                if live_limit is not None and live_limit_health["status"] == "available"
                else 0
            )
            model_for_projection = (
                self.rate_model if current_setting_a in supported_settings else ()
            )
            projection_source = "live_zoe_soc"
            setting_source = (
                PEBLAR_LIMIT_ENTITY
                if current_setting_a in supported_settings
                else "unsupported_or_unavailable_live_setting"
            )
            initial_zoe_soc = live_zoe_soc
        elif not zoe_candidates:
            current_setting_a = 13
            model_for_projection = self.rate_model
            projection_source = "replay_demo"
            setting_source = "replay_training_setting"
            initial_zoe_soc = 50.0
        else:
            current_setting_a = 0
            model_for_projection = ()
            projection_source = "unavailable"
            setting_source = "stale_or_invalid_zoe_soc"
            initial_zoe_soc = 0.0

        zoe_schedule = plan_price_aware_charge(
            model_for_projection,
            prices,
            now=now_local,
            earliest_start=now_local,
            departure=departure,
            initial_soc_pct=initial_zoe_soc,
            target_soc_pct=80.0,
            current_setting_a=current_setting_a,
        )
        zoe_projection = project_charge_session(
            model_for_projection,
            zoe_schedule.windows,
            initial_soc_pct=initial_zoe_soc,
            target_soc_pct=80.0,
            current_setting_a=current_setting_a,
        )
        zoe_data: dict[str, object] = {
            "source": projection_source,
            "live_soc_available": live_zoe_soc is not None,
            "soc_entity_id": zoe_entity_id,
            "input_status": zoe_health,
            "initial_soc_pct": initial_zoe_soc,
            "target_soc_pct": 80,
            "departure": departure.isoformat(),
            "current_setting_a": current_setting_a,
            "charger_limit_source": setting_source,
            "charge_rate_setting_supported": current_setting_a in supported_settings,
            "schedule_assumptions": {
                "departure_basis": "provisional_next_07_00_local",
                "target_soc_basis": "provisional_demo_target_80_percent",
            },
            "schedule_valid": zoe_schedule.valid,
            "schedule_reason": zoe_schedule.reason,
            "schedule_diagnostics": {
                "planner_now": now_local.isoformat(),
                "earliest_start": now_local.isoformat(),
                "departure": departure.isoformat(),
                "price_valid": prices.valid,
                "price_error_reason": prices.error_reason,
                "future_interval_count": len(prices.future),
                "first_future_start": (
                    prices.future[0].start.isoformat() if prices.future else None
                ),
                "last_future_end": (
                    prices.future[-1].end.isoformat() if prices.future else None
                ),
            },
            "required_charge_hours": zoe_schedule.required_duration_hours,
            "price_basis": zoe_schedule.price_basis,
            "estimated_import_cost_eur": zoe_schedule.estimated_import_cost_eur,
            "selected_intervals": [
                _price_interval(item) for item in zoe_schedule.selected_intervals
            ],
            "charge_windows": [
                {"start": window.start.isoformat(), "end": window.end.isoformat()}
                for window in zoe_schedule.windows
            ],
            "projection": zoe_projection.as_dict(),
            "training": [
                {
                    "current_setting_a": estimate.current_setting_a,
                    "soc_band": estimate.band,
                    "rate_pct_per_hour": estimate.rate_pct_per_hour,
                    "sessions": estimate.training_sessions,
                    "hours": round(estimate.training_hours, 2),
                    "confidence": estimate.confidence,
                }
                for estimate in self.rate_model
            ],
        }

        peb_state = self.hass.states.get(PEBLAR_STATE_ENTITY)
        peb_power_state = self.hass.states.get(PEBLAR_POWER_ENTITY)
        peb_charge_enable_state = self.hass.states.get(PEBLAR_CHARGE_ENABLE_ENTITY)
        peb_mode_state = self.hass.states.get(PEBLAR_MODE_ENTITY)
        peb_limit_health = _state_health(
            live_limit_state, now=now, maximum_age=PEBLAR_MAX_AGE
        )
        peb_state_health = _state_health(peb_state, now=now, maximum_age=PEBLAR_MAX_AGE)
        peb_power_health = _state_health(
            peb_power_state, now=now, maximum_age=PEBLAR_MAX_AGE
        )
        peb_charge_enable_health = _state_health(
            peb_charge_enable_state, now=now, maximum_age=PEBLAR_MAX_AGE
        )
        peb_mode_health = _state_health(
            peb_mode_state, now=now, maximum_age=PEBLAR_MODE_MAX_AGE
        )
        peb_available = all(
            health["status"] == "available"
            for health in (peb_state_health, peb_power_health, peb_limit_health)
        )
        input_status = {
            "growatt": {
                "entity_id": GROWATT_SOC_ENTITY,
                **growatt_health,
                "ac_charge_entity": GROWATT_AC_CHARGE_ENTITY,
                "ac_charge": (
                    growatt_ac_charge_state.state if growatt_ac_charge_state else None
                ),
                "ac_charge_health": growatt_ac_charge_health,
                "power_control_entity": GROWATT_POWER_CONTROL_ENTITY,
                "power_control": (
                    growatt_power_control_state.state
                    if growatt_power_control_state
                    else None
                ),
                "power_control_health": growatt_power_control_health,
            },
            "zonneplan": {
                "entity_id": PRICE_ENTITY,
                **price_health,
                "valid": prices.valid,
                "reason": prices.error_reason,
                "forecast_intervals": len(prices.future),
                "price_basis": (
                    prices.current.price_basis.value if prices.current else None
                ),
            },
            "peblar": {
                "state_entity": PEBLAR_STATE_ENTITY,
                "status": "available" if peb_available else "incomplete",
                "state": peb_state.state if peb_state else None,
                "state_health": peb_state_health,
                "power_entity": PEBLAR_POWER_ENTITY,
                "power_w": _numeric_state(peb_power_state),
                "power_health": peb_power_health,
                "current_limit_a": live_limit,
                "current_limit_health": peb_limit_health,
                "charge_enable": (
                    peb_charge_enable_state.state if peb_charge_enable_state else None
                ),
                "charge_enable_health": peb_charge_enable_health,
                "smart_charging_mode": (
                    peb_mode_state.state if peb_mode_state else None
                ),
                "smart_charging_mode_health": peb_mode_health,
            },
            "zoe": {
                "live_soc_entity": zoe_entity_id,
                "live_soc_available": live_zoe_soc is not None,
                "using_replay_demo": projection_source == "replay_demo",
                **zoe_health,
            },
        }
        required_inputs_available = all(
            (
                growatt_health["status"] == "available",
                price_health["status"] == "available" and prices.valid,
                peb_available,
                live_zoe_soc is not None,
            )
        )
        current = prices.current
        return {
            "updated_at": now.isoformat(),
            "input_status": (
                "connected" if required_inputs_available else "incomplete"
            ),
            "input_details": input_status,
            "battery_plan_status": battery_plan_data["decision"],
            "battery_plan": battery_plan_data,
            "zoe_projection_status": (
                zoe_data["source"] if zoe_projection.valid else "unavailable"
            ),
            "zoe_projection": zoe_data,
            "current_price": (
                float(current.import_price)
                if prices.valid and current and current.import_price is not None
                else None
            ),
            "price_basis": current.price_basis.value if current else None,
            "price_trends": {
                "moving_average_1h": (
                    float(trends.moving_average_1h)
                    if trends.moving_average_1h is not None
                    else None
                ),
                "mean_24h": (
                    float(trends.mean_24h) if trends.mean_24h is not None else None
                ),
                "coverage_1h_minutes": round(
                    trends.coverage_1h.total_seconds() / 60, 1
                ),
                "coverage_24h_hours": round(
                    trends.coverage_24h.total_seconds() / 3600, 1
                ),
                "observations_24h": trends.observations_24h,
            },
            "price_moving_average_1h": (
                float(trends.moving_average_1h)
                if trends.moving_average_1h is not None
                else None
            ),
            "price_mean_24h": (
                float(trends.mean_24h) if trends.mean_24h is not None else None
            ),
        }


class EmsShadowSensor(CoordinatorEntity[EmsShadowCoordinator], SensorEntity):
    """One read-only state from the shared coordinator snapshot."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: EmsShadowCoordinator,
        *,
        key: str,
        name: str,
        state_class: SensorStateClass | None = None,
        unit: str | None = None,
    ) -> None:
        """Initialize a read-only snapshot sensor."""
        super().__init__(coordinator)
        self.key = key
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        if key == "current_price":
            self._attr_suggested_display_precision = 4

    @property
    def suggested_object_id(self) -> str:
        """Return a stable object ID independent of the translated name."""
        return f"{DOMAIN}_{self.key}"

    @property
    def native_value(self) -> str | int | float | None:
        """Return this sensor's scalar value from the shared snapshot."""
        value = self.coordinator.data.get(self.key)
        if value is None or isinstance(value, (str, int, float)):
            return value
        return str(value)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Expose detailed inputs, projection, and planning assumptions."""
        if self.key == "input_status":
            return cast(
                Mapping[str, Any],
                {
                    "snapshot_updated_at": self.coordinator.data["updated_at"],
                    **self.coordinator.data["input_details"],
                },
            )
        if self.key == "battery_plan_status":
            return cast(
                Mapping[str, Any], self.coordinator.data.get("battery_plan", {})
            )
        if self.key == "zoe_projection_status":
            return cast(
                Mapping[str, Any], self.coordinator.data.get("zoe_projection", {})
            )
        if self.key in {"current_price", "price_moving_average_1h", "price_mean_24h"}:
            return {
                "updated_at": self.coordinator.data.get("updated_at"),
                "price_basis": self.coordinator.data.get("price_basis"),
                "trends": self.coordinator.data.get("price_trends", {}),
            }
        return {}


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Expose read-only input, planner, projection, and price trend sensors."""

    rate_model = await hass.async_add_executor_job(load_replay_rate_model)
    coordinator = EmsShadowCoordinator(hass, rate_model)
    await coordinator.async_refresh()
    async_add_entities(
        [
            EmsShadowSensor(
                coordinator,
                key="input_status",
                name="EMS input status",
            ),
            EmsShadowSensor(
                coordinator,
                key="battery_plan_status",
                name="EMS battery plan",
            ),
            EmsShadowSensor(
                coordinator,
                key="zoe_projection_status",
                name="Zoe charge projection",
            ),
            EmsShadowSensor(
                coordinator,
                key="current_price",
                name="Zonneplan current all-in price",
                state_class=SensorStateClass.MEASUREMENT,
                unit="€/kWh",
            ),
            EmsShadowSensor(
                coordinator,
                key="price_moving_average_1h",
                name="Zonneplan moving average 1 hour",
                state_class=SensorStateClass.MEASUREMENT,
                unit="€/kWh",
            ),
            EmsShadowSensor(
                coordinator,
                key="price_mean_24h",
                name="Zonneplan mean price 24 hours",
                state_class=SensorStateClass.MEASUREMENT,
                unit="€/kWh",
            ),
        ]
    )
    if not hass.is_running:

        @callback
        def _refresh_after_start(event: Event) -> None:
            hass.async_create_task(coordinator.async_refresh())

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _refresh_after_start)
