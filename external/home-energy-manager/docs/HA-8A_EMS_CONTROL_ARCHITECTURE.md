# HA-8A: Home Energy Manager control contract and write-budget architecture

Status: architecture and read-only spike; no production EMS implementation

Date: 2026-09-06

This document defines the boundary for a future Home Energy Manager (HEM). It
does not add production energy control, Growatt writes, schedule changes,
Peblar control, or production deployment.

## Evidence scope

Three different runtime contexts must not be conflated:

| Context | Observed version/surface | Purpose |
| --- | --- | --- |
| Live RPi | Home Assistant 2025.9.3; deployed `growatt_local`; endpoint `192.168.1.148:5020` | Production entity, Energy dashboard, and Recorder contract |
| HA-core devcontainer | Home Assistant 2026.9 tree; HA-7C Growatt branch `90f1be8` | Development and HIL validation |
| Shared inverter/broker | Live MIN 6000TL-XH through broker endpoint `:5021` | Read-only HIL access to the live inverter |

The devcontainer's live broker access is useful for validation, but its entity
registry and integration version are not the production contract. The live RPi
configuration is authoritative for compatibility decisions.

The live device is a single-phase MIN 6000TL-XH, configured for a 1 x 35 A
service. The live Growatt entry uses unit 1, socket framing, a 60 second scan
interval, and has power scanning disabled.

## Placement and ownership

The HEM should be a separate project, provisionally named
`home-energy-manager`, with a Home Assistant domain such as
`home_energy_manager`. It should consume stable Home Assistant entities and
provider interfaces; it must not import Growatt internals or issue raw Modbus
operations.

The Growatt integration remains responsible for protocol transport, register
decoding, entity identity, and typed device operations. A future HEM provider
adapter may translate a reviewed logical operation into a Growatt integration
service, but that adapter is not part of HA-8A.

No HEM source tree is scaffolded by this task. The intended separation is:

```text
home-energy-manager/
  coordinator.py       # state/freshness aggregation
  planner.py           # pure decision logic
  executor.py          # budgets, verification, reconciliation
  providers/           # HA-facing provider contracts
  diagnostics.py       # reasons, rejects, stale data, write history
```

## Existing production Home Assistant contract

The live RPi has 94 Growatt entities. The following entities are used by the
live Energy dashboard and are the minimum migration baseline:

| Entity | Unique ID | Quantity/source | Unit; device/state class | Counter semantics |
| --- | --- | --- | --- | --- |
| `sensor.growatt_input_1_total_energy` | `growatt_local_SNL0CGV020_input_1_energy_total` | PV input 1; FC04 `I3057-I3058` | kWh; energy/total_increasing | Lifetime counter |
| `sensor.growatt_input_2_total_energy` | `growatt_local_SNL0CGV020_input_2_energy_total` | PV input 2; FC04 `I3061-I3062` | kWh; energy/total_increasing | Lifetime counter |
| `sensor.growatt_battery_discharged_total` | `growatt_local_SNL0CGV020_discharge_energy_total` | Battery discharge; FC04 `I3127-I3128` | kWh; energy/total_increasing | Lifetime counter |
| `sensor.growatt_battery_charged_total` | `growatt_local_SNL0CGV020_charge_energy_total` | Battery charge; FC04 `I3131-I3132` | kWh; energy/total_increasing | Lifetime counter |
| `sensor.growatt_energy_to_user_today` | `growatt_local_SNL0CGV020_energy_to_user_today` | Inverter-to-user energy; FC04 `I3067-I3068` | kWh; energy/total_increasing | Daily-reset counter |

Recorder long-term statistics exist for all five rows. The live Energy
configuration also uses P1 REST cumulative grid-import/export entities and
Shelly `sensor.zoef_energy` for EV energy. Those entities are outside the
Growatt source migration but are part of the dashboard contract.

The complete live inventory, including entity IDs, unique IDs, classes, units,
source registers, and Recorder metadata, was inspected from the RPi's
`.storage` files and `home-assistant_v2.db`. The devcontainer's
`sensor.min_6000tl_xh_ha5_correction_*` names are not valid production
migration targets.

A register-source migration may preserve an existing entity only when the
physical quantity, sign convention, unit, class, and reset/counter semantics
remain identical. It must preserve `entity_id`, `unique_id`, device class,
state class, and unit whenever possible. A different semantic quantity gets a
new entity. No replacement entity is justified merely because a register is
newer or preferred.

For instantaneous values, old and new sources require side-by-side agreement.
For cumulative energy values, interval deltas, reset/rollover behaviour, and
Recorder continuity must agree before cutover. In particular,
`energy_to_user_today` is a dashboard-selected daily-reset counter and must
not silently be treated as a lifetime counter.

## Existing Growatt surfaces and accepted read semantics

The accepted HA-7C MIN/TL-XH mapping provides the following read-only inputs
for a future provider. FC03/FC04 and the holding/input table are always kept
distinct; for example, H3049 is AC-charge enable while I3049 is an energy
word.

| Semantic group | Accepted physical source |
| --- | --- |
| PV total/input power | FC04 `I3001-I3002` |
| PV1/PV2 power | FC04 `I3005-I3006`, `I3009-I3010` |
| Output, user, grid, and load power | FC04 `I3023-I3024`, `I3041-I3042`, `I3043-I3044`, `I3045-I3046` |
| Battery SOC/voltage/current | FC04 `I3171`, `I3169`, `I3170` |
| BMS SOC/current | FC04 `I3215`, `I3217` |
| Battery charge/discharge energy | FC04 `I3125-I3132` |
| AC charge enable | holding `H3049` |
| Schedule rates and stop SOCs | holding `H3036-H3059`, `H3047-H3048`, `H3082` |
| Inverter power control | holding `H0` |
| Priority word | FC04 `I3144`; not currently exposed |

The current integration exposes entity-based writes for AC charge and power
control. It has no typed schedule/priority service, no persistent write
accounting, and no read-before-write/readback contract. The schedule and
priority addresses therefore remain future provider work. `I3144` is a new
read-only diagnostic candidate, not a replacement for an existing entity.

## HEM state vector

The HEM coordinator should expose a typed snapshot with value, source, unit,
timestamp, and freshness for every field. Unknown or stale is different from
zero.

```text
grid_import_power_w       grid_export_power_w       grid_voltage_v
service_current_limit_a   phase_count               safety_margin_a
house_load_power_w        pv_power_w                battery_power_w
battery_soc_pct           battery_charge_limit_a   battery_discharge_limit_a
ev_connected               ev_charging              ev_power_w
ev_current_limit_a        ev_energy_session_kwh     ev_energy_total_kwh
ev_target_soc_pct         ev_departure              ev_priority
energy_price_now          energy_price_next        price_fresh
growatt_priority_actual    growatt_priority_source  growatt_schedule_actual
```

MVP fields are measured grid import/export, load, PV, battery SOC/power,
service limit, phase count, EV connection/charge/current/power, and freshness.
Price, departure, target SOC, and Growatt priority/schedule feedback are
provider-dependent extensions. A provider must declare capability and
freshness; the planner must not infer unavailable values.

## Actuator classes and write policy

Every future actuator belongs to one of these classes:

| Class | Example | HA-8A policy |
| --- | --- | --- |
| `FAST_RUNTIME` | Peblar charge-current limit | May be adjusted by a bounded controller after explicit provider validation |
| `SLOW_OPERATIONAL` | EV start/pause or a reviewed operating-mode change | Event-driven and rate-limited; no periodic replay |
| `PERSISTENT_OR_UNKNOWN` | Growatt H0, H3049, H3036-H3059, H3047-H3048, H3082 | No HEM writes until persistence, reboot effect, ownership, and readback are proven |

The HEM planner emits a logical intent, not a register write:

```text
desired_intent -> capability/ownership checks -> safety checks
               -> write budget -> provider operation -> readback
               -> reconciliation and diagnostic result
```

Each operation records at least:

```text
attempted, skipped, accepted, verified, or rejected
entity/provider, logical control, old value, requested value, actual value
reason, timestamp, correlation id, budget bucket, error/exception
```

The executor must read the current value, skip an unchanged value, write only
when permitted, and verify by readback. A failed or stale verification does
not get retried in a tight loop. Budgets are per actuator and per device,
with a quiet period and a daily/change budget where the provider supports it.
HA-8A intentionally does not invent a safe endurance number; that is a
device/provider acceptance parameter.

Growatt's vendor-native minimum command period is approximately 850 ms with a
1 second recommendation for the applicable protocol family. The HEM must not
turn the 1 Hz transport budget into a control loop: telemetry reads, writes,
readback, and reconciliation share a serialized provider budget. Future
schedule operations must be sparse and explicitly owned.

## Operating states and arbitration

The planner should be a pure function of a snapshot, policy, capabilities,
and current operating state. Initial states are:

| State | Intent |
| --- | --- |
| `SELF_CONSUMPTION` | Keep the house supplied and avoid unnecessary grid import |
| `CHEAP_CHARGE` | Charge within the configured price/window and device limits |
| `PROFIT_EXPORT` | Export only after reserve, load, and safety constraints |
| `FAILSAFE` | Freeze or reduce discretionary actions when required data is stale or unsafe |

FAILSAFE must not repeatedly rewrite the inverter. It should hold the last
verified safe state, reduce optional EV demand if that is a validated fast
actuator, and surface the reason.

The live service constraint is one phase and 35 A. The planner must reserve a
configurable safety margin and use measured grid current/power as the primary
constraint. It must not assume that the battery is a fuse-protection device.

For EV/ARK arbitration, the MVP owns only the EV current-limit decision and
must yield to a higher-priority safety constraint. A future provider should
make these priorities explicit:

```text
service/fuse safety > vehicle/charger safety > house load > battery reserve
> configured EV departure need > tariff optimisation > export optimisation
```

The ARK battery is the energy buffer. PV surplus first serves the house, then
the selected battery/EV policy; charging the EV must not cause a service-limit
violation. When no validated price provider exists, the planner falls back to
local measurements and configured defaults rather than fabricating a tariff.

## September MVP boundary

The MVP target for 23 September 2026 is a read-only, testable HEM contract:

1. typed state snapshot and freshness handling;
2. live P1/grid, Growatt, and Peblar provider capability inventory;
3. pure planner with the four operating states and 1 x 35 A constraint;
4. dry-run actuator intents with reason codes and budget accounting;
5. diagnostics showing stale data, rejected actions, and ownership;
6. compatibility tests protecting the five Energy-dashboard Growatt entities.

It does not include production writes, Growatt schedule changes, priority
changes, automatic Peblar control, Zonneplan integration, or deployment to
the live RPi. The next implementation task must first validate typed
schedule/priority feedback and the actual price/EV provider surfaces.

## Safety and handoff

No Modbus write, HA service call, production entity migration, or deployment
was performed for HA-8A. Existing `growatt_local` runtime code was not
changed. The document is an architecture checkpoint for HA-8B and later
provider work; it is not authorization to operate the live inverter.
