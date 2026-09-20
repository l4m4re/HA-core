# HA-8B: EMS public surfaces and provider contracts

Status: feedback plus explicit TL-XH TOU controls; no tariff or control policy

Date: 2026-09-06

HA-8B continues the HA-8A architecture. The Growatt integration provides
device-driver data, bounded feedback, and the inverter's explicit nine-period
TOU controls. EMS policy, tariff choice, and arbitration remain outside
`growatt_local`.

## Compatibility contract

The production compatibility baseline is the live RPi installation, not the
HA 2026.9 devcontainer. The devcontainer reaches the live inverter through
the broker for HIL reads, but it has a different HA version, integration
branch, entity registry, and Recorder database.

The regression fixture
`tests/fixtures/production_sensor_contract.json` freezes the five verified
Growatt entities used by the live Energy dashboard:

| Entity/statistic ID | Unique ID | Source | Meaning | Unit/classes | Counter |
| --- | --- | --- | --- | --- | --- |
| `sensor.growatt_input_1_total_energy` | `growatt_local_SNL0CGV020_input_1_energy_total` | FC04 I3057-I3058 | PV input 1 lifetime energy | kWh; energy/total_increasing | lifetime |
| `sensor.growatt_input_2_total_energy` | `growatt_local_SNL0CGV020_input_2_energy_total` | FC04 I3061-I3062 | PV input 2 lifetime energy | kWh; energy/total_increasing | lifetime |
| `sensor.growatt_battery_discharged_total` | `growatt_local_SNL0CGV020_discharge_energy_total` | FC04 I3127-I3128 | battery discharged lifetime energy | kWh; energy/total_increasing | lifetime |
| `sensor.growatt_battery_charged_total` | `growatt_local_SNL0CGV020_charge_energy_total` | FC04 I3131-I3132 | battery charged lifetime energy | kWh; energy/total_increasing | lifetime |
| `sensor.growatt_energy_to_user_today` | `growatt_local_SNL0CGV020_energy_to_user_today` | FC04 I3067-I3068 | inverter-to-user daily energy | kWh; energy/total_increasing | daily reset |

All five have verified Recorder long-term statistics. The fixture also
records the `growatt_local` platform, positive accumulation convention, and
the current decoder scale of 10. The live Energy configuration additionally
uses P1 REST cumulative import/export entities:

```text
sensor.p1_energy_consumption_tariff_1  unique_id=p1-t1
sensor.p1_energy_consumption_tariff_2  unique_id=p1-t2
sensor.p1_energy_returned_tariff_1    unique_id=p1-rt1
sensor.p1_energy_returned_tariff_2    unique_id=p1-rt2
```

It also uses Shelly `sensor.zoef_energy` for EV energy. These non-Growatt
entities are not renamed or remapped by HA-8B.

No existing `entity_id`, `unique_id`, device class, state class, unit,
physical meaning, sign convention, or source mapping changed. In particular,
I3170 remains the storage-device/BDC-side battery current (`unsigned /10`,
signedness unresolved) and I3217 remains the distinct BMS current (`signed
int16 /100`). No existing public battery-current entity was switched between
them.

Future source migration remains an explicit overlap-reviewed operation. A
cumulative counter requires matching interval deltas, understood reset and
rollover behaviour, no artificial jump/reset, and Recorder continuity before
cutover.

## Growatt feedback and TOU control surface

The integration now exposes three additive read-only entities for the
`HYBRID_120_TL_XH` family. They use the existing native MIN block polling;
they do not add one Modbus transaction per entity.

| Surface | Source | Public state | Attributes |
| --- | --- | --- | --- |
| `sensor.growatt_current_priority` | FC04 I3144 | `load_first`, `battery_first`, `grid_first`, or `unknown_<raw>` | `raw_value`, `mode`, `valid`, `observed_at` |
| `sensor.growatt_xh_schedule` | FC03 H3038-H3045 and H3050-H3059; H3046 reserved and H3049 remains separate AC-charge state | `valid`, `invalid`, or unavailable | bounded `slots` list, `decode_valid`, `observed_at` |
| `sensor.growatt_xh_tou_settings` | FC03 H3036-H3049 and H3082 | `valid` or unavailable | grid-first and battery-first limits, AC-charge enable, load-first stop SOC, `observed_at` |

The unique-ID basis is additive and deterministic:

```text
growatt_local_<serial>_current_priority
growatt_local_<serial>_xh_schedule
growatt_local_<serial>_xh_tou_settings
```

I3144 raw values 0, 1, and 2 decode to Load First, Battery First, and Grid
First. Unsupported values remain visible as raw values and are never coerced
to Load First.

The schedule entity contains exactly nine structured slot records. Each record
contains slot number, start/end time, priority state and raw value, enabled,
both source words, and a validity flag. This gives a separate EMS enough
information to inspect configured slots and actual priority without importing
Growatt Python internals or exposing hundreds of raw-register entities.

The TOU settings entity retains the scalar limits separately from the schedule:
grid-first discharge rate and stop SOC, battery-first charge rate and stop SOC,
AC-charge enable, and load-first stop SOC. It remains read-only. H3049 is a
global AC-charge permission and remains exposed through the existing
`switch.growatt_ac_charge` compatibility surface; it is not duplicated on each
TOU period.

Each TL-XH period also has four explicit controls:

| Control pattern | Count | Meaning |
| --- | ---: | --- |
| `select.<name>_tou_<n>_priority` | 9 | `load_first`, `battery_first`, or `grid_first` |
| `time.<name>_tou_<n>_start` / `_end` | 18 | period start and end in local inverter time |
| `switch.<name>_tou_<n>_enabled` | 9 | enable bit in the period's packed start word |

Changing any one control writes the complete two-register period pair with
Modbus FC10. The other fields are preserved, including the priority and enable
bits when a time is changed. Writes are serialized, wait 11 seconds for the
broker cache, and force a fresh readback; a mismatch raises a Home Assistant
service error instead of leaving an optimistic state.

HA-7B live evidence is covered by deterministic tests:

```text
H3038=0x3700, H3039=0x173B -> 23:00-23:59, Battery First, disabled
H3040=0xA000, H3041=0x0700 -> 00:00-07:00, Battery First, enabled
H3042=0x2000, H3043=0x043B -> 00:00-04:59, Battery First, disabled
H3044-H3045 and H3050-H3059 -> zero/disabled
```

The separate TL-XH US H3125+ model is not conflated with this nine-slot XH
model.

## Existing schedule/control inventory

The API mapping contains typed metadata for the relevant holding registers and
the controls above use the following write/readback surface:

| Register(s) | Existing API object | Existing HA surface | HA-8A class | EMS use in HA-8B |
| --- | --- | --- | --- | --- |
| H3036 | `GrowattDeviceRegisters`, R/W metadata | none | persistent-or-unknown | read metadata only |
| H3037 | `GrowattDeviceRegisters`, R/W metadata | none | persistent-or-unknown | read metadata only |
| H3038-H3059 | raw typed register metadata; H3046 reserved | schedule sensor plus nine TOU control groups | persistent-or-unknown | FC10 pair write with readback |
| H3047 | `GrowattDeviceRegisters`, R/W metadata | none | persistent-or-unknown | read metadata only |
| H3048 | `GrowattDeviceRegisters`, R/W metadata | none | persistent-or-unknown | read metadata only |
| H3049 | existing sensor and AC-charge switch | `sensor.growatt_ac_charge_enabled`, `switch.growatt_ac_charge` | persistent-or-unknown | global AC-charge compatibility surface |
| H3082 | `GrowattDeviceRegisters`, R/W metadata | none | persistent-or-unknown | read metadata only |
| H0 | existing power-control register | conditional `switch.growatt_power_control` | persistent-or-unknown | existing compatibility surface unchanged |
| I3144 | new typed register mapping | additive current-priority sensor | read-only feedback | EMS feedback |

Modbus writability is not treated as runtime safety. The machine-readable
metadata in `ems_contract.controls` requires write-on-change and readback for
all listed persistent/unknown controls, leaves minimum cadence as an explicit
placeholder, and contains no invented flash/EEPROM endurance value.

## Schedule model and continuity rules

`ems_contract.growatt` contains the pure typed model:

```text
PriorityMode: LOAD_FIRST=0, BATTERY_FIRST=1, GRID_FIRST=2
PriorityWord: raw, known mode or unknown raw value
XhScheduleSlot: slot 1..9, start, end, priority, enabled,
                raw_start_word, raw_end_word
```

The packed start word uses minute bits 0-7, hour bits 8-12, priority bits
13-14, and enable bit 15. The end word uses minute bits 0-7 and hour bits
8-12. Invalid times and unknown priorities remain observable and make the
slot invalid; they are not silently normalized.

No existing entity is repurposed. The public chain remains:

```text
physical register -> decoded quantity -> HA entity -> Recorder statistic
                  -> Energy dashboard/automation history
```

## Provider contracts

The small pure-Python `ems_contract` package is a local extraction point for a
future separate `home-energy-manager` project. It is not a Home Assistant EMS
integration and contains no planner or actuator calls.

### Price provider

`PriceInterval` preserves:

```text
start, end, import_price, export_price, source, retrieved_at, valid
price_basis, commodity_price, taxes_and_fees, error_reason
```

`PriceProviderState` carries the current interval, future intervals,
retrieval timestamp, validity, and error reason. The price basis distinguishes
all-in import prices from commodity-only or unknown semantics. The test
fixture provider is deterministic and read-only.

The available HA-core development tree has no verified Zonneplan integration
surface, and the live RPi has no Zonneplan config entry. Therefore HA-8B does
not invent Zonneplan entity IDs, scrape the cloud, or commit credentials. A
production adapter still needs a read-only capture of the actual current and
future price entities, units, price basis, retrieval timestamp, and validity
rules.

### EV provider

`EvProviderState` represents partial data explicitly:

```text
availability: not_configured | unavailable | available
connected, charging, current_limit_a, charging_power_w
soc_pct, target_soc_pct, departure
observed_at, soc_observed_at, valid, error_reason
```

`EvProvider` is read-only. Peblar charger state and Zoe/PyCanZE vehicle state
remain separate possible providers. A deterministic fixture provider covers
the unavailable and partial-state cases. Missing EV data is never converted
to zero SOC or a fabricated disconnected state.

## Normalized read-only snapshot and freshness

`EmsSnapshot` combines `GrowattState`, optional `PriceProviderState`, and
optional `EvProviderState`. `GrowattState` includes current priority, schedule,
telemetry values, and separate observation timestamps for telemetry, priority,
and schedule. The snapshot contains data only; it does not select cheap hours,
transition operating states, or issue controls.

The new HA entities expose `observed_at`. Provider contracts expose
`retrieved_at`/`observed_at`, validity, and error reasons. This makes stale
versus valid machine-readable for HA-8C without embedding policy in the
Growatt driver.

The new feedback entities also expose the deterministic
`sensor_contract_version=ha-8b-20260906` diagnostic attribute.

## Missing production inventory

The following were not invented or changed in HA-8B:

- exact frozen production entity/statistic IDs for instantaneous Growatt
  PV/load/grid/battery power and battery SOC;
- exact live instantaneous P1 grid-power entity IDs and their sign mapping;
- exact production Zonneplan current/future-price entity/service surface;
- exact production Peblar or Zoe provider config/entity surface.

The smallest later read-only capture is the live RPi entity registry and
config-entry storage, supplemented by a state snapshot for the instantaneous
entities and provider timestamps. It must record entity IDs, unique IDs,
classes, units, sign, source, and Recorder/statistics metadata before any EMS
provider is enabled.

## Tests and write boundary

Focused tests cover:

- the five production sensor/Recorder semantics and unique-ID basis;
- I3170/I3217 distinction and holding/input H3049 distinction;
- I3144 values 0/1/2 and unknown raw values;
- HA-7B Time 1/2/3, disabled slots, raw-word retention, and invalid priority;
- persistent-control no-op/readback metadata;
- TOU word packing, per-period control preservation, FC10 arguments, and
  staging-HA service readback;
- valid price intervals, stale price state, unavailable EV state, partial EV
  state, and deterministic normalized snapshots.

The staging HA instance performed a controlled HIL test on disabled period 2:
its end time was written from 19:58 to 23:55 and then restored to 19:58. Both
FC10 writes were acknowledged, the post-cache readbacks matched, and the period
remained disabled. No production HA deployment or non-TOU control was changed.
The HA-core parent gitlink was not changed.
