# HA-GII-6 production upgrade readiness and rollback gate

Status: read-only readiness review. No production files, Home Assistant
configuration, Recorder data, broker settings, inverter settings, or Shine
capture were changed.

## Disposition

`HA_GII_PRODUCTION_UPGRADE_READY_WITH_PRECONDITIONS`

The reconciled read-side integration is suitable for a controlled production
cutover, but the following must be completed and explicitly recorded first:

1. Create and verify a fresh supported full Home Assistant backup containing
   the current Recorder database, configuration, `.storage`, and `share`.
2. Rehearse the candidate against the actual production Core line, or upgrade
   production Core to a supported 2026.9.x build before installing the
   candidate. HA-GII-5 validated Core 2026.9.0; production is still on
   2025.9.3.
3. Record the pre-cutover entity/statistics manifest and accept the two
   additive XH feedback entities described below.
4. At cutover, verify that the production reactive-power statistic ID has no
   incompatible historical `W` metadata. The current production database has
   no such row; if one appears before cutover, stop and obtain approval for
   the bounded statistics migration in §7.

These are cutover gates, not reasons to alter the currently stable production
installation. The existing long-running Shine capture remains active and is
not part of the cutover.

## Exact revisions and environments

| Item | Revision/version | Evidence |
| --- | --- | --- |
| Production Growatt source | `fix/min-6000xh`, `615c4623e22b8dcfb83047ef5cf617c6f586bf34` | clean Git checkout on RPi |
| Candidate consumer branch | `integration/register-spec-consolidation-20260911`, `d9b0647bf14a260b616435bcaaa21df4f1cc3747` | candidate after HA-GII-5 documentation |
| Candidate runtime tested | `1409300467e5fe2ce48124b6f0516574f2d3189a` | HA-GII-5 HIL run |
| Canonical GII | `main`, `5fa71e87ac89f66b13dcf1599834a2f7a446981b` | current `growatt-inverter-info` |
| HA-GII-5 Core | `1f3748d9310fad0a9b22ceec17654fcb8d42069f`, Core 2026.9.0 | disposable dev HA |
| Production Core | 2025.9.3 | RPi live container |
| Production OS/Supervisor | Home Assistant OS 16.1 / Supervisor 2026.09.0 | `ha info` |
| Production PyModbus | 3.11.1 | live Core container |

The production HA container has been running since 2026-09-05T17:04:51Z
with restart count 0. Supervisor reports Core 2026.9.1 as the latest stable
version and currently reports the installation as unsupported. This report
does not upgrade it.

## Production installation and configuration

Production uses a manually maintained checkout, not an HACS-managed component:

```text
/config/custom_components/growatt_local
  -> /share/custom_components/Homeassistant-Growatt-Local-Modbus/
     custom_components/growatt_local
```

The checkout is clean and is on the `fix/min-6000xh` branch at the revision
above. The installed manifest is version `0.1`; the candidate manifest is
version `0.2.1` and requires `pymodbus>=3.11.1`, which the live container
already provides.

The live config entry is:

| Field | Value |
| --- | --- |
| model/type | `MIN 6000TL-XH` / `hybrid_120_TL_XH` |
| serial | `SNL0CGV020` |
| transport | TCP, Modbus frame `socket` |
| host/port/unit | `192.168.1.148:5020`, unit 1 |
| scan interval | 60 s |
| power scan | disabled; configured interval 5 s |
| inverter power control | disabled |

The current live entity registry contains 94 Growatt entries, 93 distinct
unique IDs, and no disabled Growatt entries. Device identity is the existing
Growatt device (`MIN 6000TL-XH`, identifier `growatt_local/SNL0CGV020`).

## Entity and source continuity matrix

The candidate keeps the existing entity-ID and unique-ID construction. Existing
Energy-dashboard entities are not renamed. Physical source addresses below are
unchanged unless the table explicitly says that only decoding/presentation
changes.

| Existing entity | Unique-ID suffix | Source before | Candidate source | Public change and continuity |
| --- | --- | --- | --- | --- |
| `sensor.growatt_total_energy_produced` | `output_energy_total` | input I3051 | input I3051 | kWh, energy, `total_increasing`; unchanged |
| `sensor.growatt_energy_to_user_total` | `energy_to_user_total` | input I3069 | input I3069 | kWh, energy, `total_increasing`; unchanged |
| `sensor.growatt_energy_to_grid_total` | `energy_to_grid_total` | input I3073 | input I3073 | kWh, energy, `total_increasing`; unchanged |
| `sensor.growatt_battery_charged_total` | `charge_energy_total` | input I3131 | input I3131 | kWh, energy, `total_increasing`; unchanged |
| `sensor.growatt_battery_discharged_total` | `discharge_energy_total` | input I3127 | input I3127 | kWh, energy, `total_increasing`; unchanged |
| `sensor.growatt_battery_charged_today` | `charge_energy_today` | input I3129 | input I3129 | kWh, daily reset, existing ID retained |
| `sensor.growatt_battery_discharged_today` | `discharge_energy_today` | input I3125 | input I3125 | kWh, daily reset, existing ID retained |
| `sensor.growatt_reactive_wattage` | `output_reactive_power` | input I3021 | input I3021 | same physical quantity; `W/power` becomes `var/reactive_power/measurement` |
| `sensor.growatt_battery_current` | `battery_current` | input I3170 | input I3170 | A, non-negative BDC magnitude `/10`; same ID and meaning |
| `sensor.growatt_bms_battery_current` | `bms_battery_current` | input I3217 | input I3217 | A, signed BMS current `/100`; same ID, corrected decoding |
| `sensor.growatt_soc` | `soc` | input I3171 | input I3171 | %, battery SOC; unchanged |
| `sensor.growatt_battery_voltage` | `battery_voltage` | input I3169 | input I3169 | V; unchanged |
| `sensor.growatt_discharge_power` | `discharge_power` | input I3178 | input I3178 | W, signed decoder; same quantity/ID |
| `sensor.growatt_charge_power` | `charge_power` | input I3180 | input I3180 | W, signed decoder; same quantity/ID |
| `sensor.growatt_power_to_grid` | `power_to_grid` | input I3043 | input I3043 | W, signed decoder; same quantity/ID |
| `sensor.growatt_power_user_load` | `power_user_load` | input I3045 | input I3045 | W, signed decoder; same quantity/ID |
| `sensor.growatt_power_to_user` | `power_to_user` | input I3041 | input I3041 | W, signed decoder; same quantity/ID |

The candidate also explicitly creates these additive, read-only XH feedback
entities for `hybrid_120_TL_XH`:

| New entity | Unique ID | Source | Purpose |
| --- | --- | --- | --- |
| `sensor.growatt_current_priority` | `current_priority` | input I3144 | decoded current priority with raw value retained |
| `sensor.growatt_xh_schedule` | `xh_schedule` | holding H3038-H3059 | nine bounded schedule slots with raw words retained |

The existing production count of 94 therefore predicts 96 registry entries
after a successful candidate setup, subject to Home Assistant retaining the
same registry rows. Any entity-ID or unique-ID change outside the two named
additions is a rollback condition. The candidate does not create the optional
output-power-limit number entity because production has
`inverter_power_control=false`.

The candidate changes the read plan, not the public sensor identity. For the
MIN/TL-XH family it requests vendor-native blocks and decodes selected words
locally:

```text
FAST:       FC04 3000/125, FC04 3125/125
CONTROL:    FC03 3000/125
STATIC:     FC03 0/125
DIAGNOSTIC: FC04 3250/125
```

No one-register-per-entity polling is implied by the candidate.

## Existing `ac_charge_enabled` collision

Production reproduces the HA-GII-5 observation:

```text
growatt_local_SNL0CGV020_ac_charge_enabled
  sensor.growatt_ac_charge_enabled
  switch.growatt_ac_charge
```

It is pre-existing, accepted by Home Assistant, and has not produced a setup
error. The sensor and switch are separate platform domains representing the
same underlying setting; the candidate preserves both rows and does not create
another AC-charge identity. Classification: **harmless/pre-existing; not a
cutover blocker**. It should remain a separately reviewed cleanup, not be
silently “fixed” during this upgrade.

## Reactive power statistics boundary

The production entity currently reports:

```text
entity:       sensor.growatt_reactive_wattage
unit:         W
device_class: power
state_class:  absent
statistic ID: sensor.growatt_reactive_wattage
```

A read-only query of the live `statistics_meta` table found **no** row for
`sensor.growatt_reactive_wattage`, and therefore no production W long-term
statistics history to preserve or convert. This differs from the disposable
HA-GII-5 database, where a legacy W metadata row existed and HA suppressed a
new var series.

The candidate correctly changes I3021 to `var`, reactive-power class, and
measurement state class. For the actual current production database this is a
clean creation of the var statistic series, not a W-to-var history migration.
Do not mathematically convert W history.

Cutover procedure for this boundary:

1. Verify the absence of the statistic metadata row immediately before
   deployment.
2. After the first successful candidate update, verify that the same statistic
   ID has `var` metadata and that no statistics warning is emitted.
3. If a W row unexpectedly exists, stop. After a verified backup and explicit
   approval, use bounded Option B: retire only the incompatible reactive-power
   metadata/history, then allow the same entity ID to start a clean var series.
   Do not delete or rewrite any other statistics.

Thus Option A is effectively satisfied in the current production state (there
is no W series); Option B is only a contingency. No production statistics were
edited in this review.

## Recorder anomalies

### Battery discharged-today sum

Live production metadata is:

```text
metadata_id: 21
statistic:   sensor.growatt_battery_discharged_today
unit:        kWh
has_sum:     1
```

The hourly series contains ordinary daily states but a polluted cumulative
sum. The first clearly pathological jump found was:

```text
2025-10-11 23:00 UTC: state 0.0, sum 7,620.8
2025-10-12 00:00 UTC: state 0.2, sum 12,780,588.6
```

The later history contains further jumps. A retained hourly row on 2026-03-15
reached raw state 2,412.3 kWh and sum 144,772,449.8 kWh, while ordinary raw
values are single-digit kWh. The latest observed sum was approximately
144,776,730.2 kWh. Short-term data around the original first jump has already
been purged, so the exact triggering sample cannot be recovered from this DB.

Classification: **historical source outlier and/or decoder/aggregation
corruption; exact original trigger unresolved**. This is not classified as a
normal reset, and it is not attributed to `total_increasing` alone. The
database contains evidence of at least one implausible source-state interval,
but the first sum jump has no retained short-term row that identifies whether
the trigger was a raw outlier, a transient decoder artifact, or a Recorder
boundary interaction.

The anomaly predates the candidate, does not change the new physical source,
and does not by itself prevent new statistics from being written. It does
pollute historical graphs and must not be presented as repaired by this
upgrade. Recorder repair is a separate, explicitly reviewed task.

### Total generated-energy -0.1 kWh step

The live state history records exactly one isolated decrease:

```text
2026-09-05 16:24:48.126960 UTC: 19501.1 kWh
2026-09-05 16:28:54.505748 UTC: 19501.0 kWh
```

The following samples recover the monotonic progression. The hourly
`total_increasing` statistic sum did not decrease at this point, so HA did not
turn it into a cumulative negative statistic delta. The candidate's corrected
read path has not reproduced it in HA-GII-5.

Classification: **harmless historic one-sample transient; not a cutover
blocker**. The smoke test must nevertheless check for a new decrease.

## Broker `:5020` compatibility

The live broker image is:

```text
growatt-rtu-broker:ha-dev-3d-predictive-20260911c
```

It has been running since 2026-09-11T07:16:39Z with restart count 0 and the
following relevant command-line policy:

```text
--tcp 0.0.0.0:5020
--tcp-alt 0.0.0.0:5021
--sniff 0.0.0.0:5700
--mode cache+shine-predictive
--min-period 1.0 --rtimeout 4.0
```

The broker implementation constructs one `CacheGatewayService`, one
`RegisterCache`, and one downstream serial owner, then attaches the primary
and alternate TCP listeners to that same gateway. `:5020` and `:5021` thus:

* share cache contents, native block policies, serial arbitration, and the
  same read response shapes;
* differ only in source label/priority (`PROD_TCP` has priority over
  `DEV_TCP`); and
* have no separate freshness or write-permission policy.

The TCP gateway accepts FC03/FC04 read requests and can serve the candidate's
125-word native blocks on `:5020`. The TCP handler does not currently expose
FC06/FC10 write handling. That is not a dependency for this read-only
candidate, but it remains a separate prerequisite for future HA write/control
work. Shine writes continue through the separate transparent Shine path.

No broker change is required for the candidate read plan. Development must
continue to use `:5021`; `:5020` must remain reserved for production.

## Cache freshness by block

The HA-GII-5 bounded capture was
`/tmp/growatt-ha-gii5-20260911-211609.jsonl`, with 61 DEV cache hits per
native block. The following are observed DEV cache ages, not guarantees beyond
that capture:

| Block | min | median | p90 | p95 | max | physical refresh observations |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| FC04 3000/125 | 0.293 s | 41.500 s | 92.193 s | 107.692 s | 118.190 s | 3; roughly 122 s then 90 s |
| FC04 3125/125 | 0.287 s | 42.261 s | 94.292 s | 109.791 s | 120.289 s | 3; roughly 123 s then 89 s |
| FC03 3000/125 | 0.209 s | 57.146 s | 162.004 s | 171.003 s | 177.149 s | 3; roughly 190 s then 33 s |

The configured broker policies use 120 s refresh intervals for the two fast
input pages and 180 s for holding 3000, with non-Shine maximum ages of 240 s
and 360 s respectively. Holding page 0 and input page 3250 are lower-rate
blocks. The observed maximum for FC03 3000 is therefore operationally
consistent with the current predictive/background schedule, not proof of a
sub-second telemetry guarantee.

For ordinary HA display/history, an age of up to roughly 2–3 minutes is
acceptable for this current monitoring use provided the value is identified as
cached and the integration remains available. For future EMS decisions,
operational telemetry should have a hard freshness gate of **15 seconds** (and
must fail safe when older), especially for PV surplus, grid flow, battery
charge/discharge, and Peblar charging decisions. The HA-GII-5 measurements do
not meet that future control requirement consistently. This is a **future EMS
blocker**, not a blocker for the present read-side upgrade.

## Physical refresh latency

The bounded HA-GII-5 capture measured auxiliary 20/15-word reads at about
52–53 ms, native pages at about 1.4–3.96 s under mixed Shine/HA load, and one
predictive FC03 page at 7.49 s including a retry. Earlier direct native-page
observations were in the millisecond range.

The difference is best explained by the broker's single-owner serial queue,
the vendor-recommended one-second transaction pacing, Shine priority and
interleaving, predictive/background refreshes, and retry/wait time included in
the measured interval. The broker records duration from refresh start through
response/decode, so it is not an isolated inverter response-time measurement.
The evidence does not prove that the inverter itself took seconds to process
the Modbus response. Future EMS freshness must therefore be based on completed
cache age and timeout state, not on nominal register count.

## Shine and FC0x20 assessment

The existing capture was inspected without stopping or modifying it:

```text
file:    /tmp/growatt-winter-boundary-20260911-092431.jsonl
window:  2026-09-11 09:24:31.468–21:43:01.964 UTC (snapshot)
records: 210,042
bytes:   62,160,760 (snapshot)
FC20 physical refresh successes: 4,260
FC20 physical refresh failures:  227
approximate physical FC20 failure rate: 5.1%
serial reopen pairs: 49
async frames observed/forwarded: 176/176
```

The 227 failures are the already observed type of Shine FC20 physical
passthrough timeout; they are not evidence that FC20 is a standard FC03/FC04
register block. The capture also shows that valid asynchronous inverter
frames are observed and forwarded. This is a meaningful Shine transport
reliability concern, but it did not cause missing candidate HA cache hits in
the bounded HA-GII-5 run, and the live production HA link remained operational.

Classification for this read-side cutover: **monitoring concern, not a
production upgrade blocker**. The post-cutover observation must include the
sniff stream and distinguish FC20 failures from standard HA cache/physical-read
failures. The capture process remains untouched.

## Test-environment issue

The two known test failures (`test_growatt_api_read_write` and
`test_sensor_setup`) come from the checked-out simulator's address-zero
assumption becoming `SimData(address=-1)` with installed PyModbus 3.11.1.
This is a test-fixture/version incompatibility:

* production uses the real TCP broker, not that simulator;
* the live production dependency already satisfies the candidate requirement;
* no production execution path imports the simulator.

It should receive a small test-only follow-up, not a dependency upgrade mixed
into this cutover. HA-GII-5's live/HIL validation is the relevant runtime
evidence.

## Minimum backup and recovery gate

The RPi currently has an older full backup, slug `5852fb45`, named
`HA-DEV-1R-production-20260906`, created 2026-09-06T16:25:31Z, size
1,566,412,800 bytes. It includes Home Assistant, `share`, `ssl`, and the
listed add-ons, but it is not a fresh cutover backup and must not be the sole
rollback point.

Before cutover, a human operator must:

1. Run the supported Supervisor backup command, for example:

   ```text
   ha backups new --name HA-GII-6-pre-cutover-<timestamp>
   ```

   Do not use `--homeassistant-exclude-database`.
2. Verify it appears in `ha backups`, inspect it with
   `ha backups info <slug>`, and record slug, timestamp, size and checksum.
3. Preserve an exact archive/checksum of the current integration checkout at
   `615c4623…`, including the symlink/deployment path and the current manifest.
4. Record the config-entry projection, entity registry projection, device
   identity, critical current states, and statistics metadata from this report.
5. Verify that the backup contains the Recorder DB and the `share` folder.
   A test restore should be performed in a disposable environment when the
   backup tooling permits it; do not restore production as part of this task.

The backup must be created after any final user-approved settings change and
immediately before cutover. No backup was created by this audit.

## Exact cutover procedure (not executed)

1. Announce a short maintenance window and suspend user-initiated Growatt
   writes for the window. Do not change TOU or battery settings.
2. Create and verify the fresh full backup above.
3. Capture the pre-cutover manifest: Core/OS/Supervisor versions, integration
   SHA, config entry, 94 entity rows, unique-ID collision, reactive metadata,
   and critical energy/current states.
4. Stage the candidate `custom_components/growatt_local` tree outside the live
   symlink target. Verify its SHA-256 manifest and that it is exactly the
   candidate branch at `d9b0647…`.
5. Preserve the old tree as a timestamped, checksummed archive. Switch the
   `growatt_local` symlink or versioned component directory atomically so the
   old tree remains recoverable. Do not modify `.storage`, the Recorder DB,
   `configuration.yaml`, or the broker container.
6. Restart Home Assistant using the supported command `ha core restart`; a
   source replacement requires a restart rather than only a config reload.
7. Confirm the integration loads once, the config entry remains configured for
   `192.168.1.148:5020`, and the broker remains on the existing image and
   command line.
8. Run the smoke checks below for at least several 60-second polling cycles.
9. Inspect Home Assistant logs and `statistics_meta` for setup retries,
   Modbus errors, unit warnings, entity changes, or unexpected writes.
10. Declare GO only if all mandatory checks pass. Otherwise execute rollback;
    do not attempt ad-hoc Recorder or entity-registry repair during the window.

## Exact rollback procedure (not executed)

Rollback is required if the integration fails setup, creates an unexpected
entity identity, produces implausible values, loses critical energy
continuity, generates an unexpected write, or causes repeated broker/HA
timeouts.

1. Stop the cutover observation and record the failure timestamp and logs.
2. Restore the checksummed pre-cutover integration tree or atomically switch
   the symlink back to the archived `615c4623…` tree.
3. Restart Core with `ha core restart` and verify the original config entry and
   entity registry.
4. Confirm that the broker image, ports `5020/5021/5700`, serial ownership,
   Shine capture and inverter state were not changed.
5. Use the full Supervisor backup restore only if the source rollback is
   insufficient or broader HA state was changed. A full restore is not the
   first response to a component-only failure because it can roll back valid
   Recorder history and unrelated HA changes.
6. Re-run the pre-cutover smoke checks and leave the candidate disabled until
   the failure is reviewed.

If the Core version itself is upgraded as a separate prerequisite, retain a
separate backup and rollback point for that Core upgrade; do not conflate a
Core rollback with the integration source rollback.

## Post-cutover smoke test and rollback conditions

Mandatory pass checks:

* one successful integration setup, with no setup retry loop or traceback;
* 94 existing entity IDs and unique IDs unchanged;
* exactly the two expected additive XH feedback entities, with no unrelated
  identity changes;
* config entry still targets `192.168.1.148:5020`, unit 1, 60-second scan;
* no Modbus writes emitted by HA during read-only observation;
* broker container remains healthy with unchanged image, restart count and
  listener ports;
* at least three successful polling cycles with plausible PV/output/load,
  SOC, BDC current I3170, and signed BMS current I3217;
* I3170 remains a non-negative BDC magnitude, while I3217 can be negative on
  discharge and is not an unsigned ~653 A value for a `0xff..` raw word;
* total generated, grid, user, battery-charged and battery-discharged totals
  have no artificial jump or decrease;
* daily counters may reset only at the expected local midnight boundary;
* existing Energy-dashboard entity IDs, unique IDs, units and physical
  quantities remain continuous;
* `sensor.growatt_reactive_wattage` reports `var` with reactive-power class;
  production has no old W statistic row, so a clean var metadata row should be
  created without a warning;
* Recorder continues to create statistics for critical cumulative energy
  entities; the known old battery-discharged sum remains documented as
  historical pollution and is not silently rewritten;
* sniff monitoring shows normal framed Shine traffic and no new unexplained
  standard FC03/FC04 failure pattern.

Immediate rollback conditions:

* setup failure, repeated setup retries, or Core startup instability;
* any unexpected entity-ID/unique-ID rename or loss of an Energy-dashboard
  entity;
* any unexpected HA-originated write;
* a new giant counter value, new non-monotonic lifetime total, or implausible
  BMS/BDC decoding;
* missing/invalid reactive statistics metadata after the planned clean var
  transition;
* repeated production cache misses/physical timeouts that make the existing
  HA link unavailable;
* broker restart, port loss, Shine failure materially beyond the observed
  baseline, or evidence that the production endpoint no longer shares the
  expected read gateway.

## Deferred work and boundaries

The following remain outside this gate:

* TCP FC06/FC10 write support in the broker;
* Recorder repair or conversion of the polluted battery-discharged history;
* resolving every BMS temperature/diagnostic uncertainty;
* guaranteeing the 15-second freshness contract required by future EMS
  control;
* fixing the PyModbus simulator fixture;
* any broker scheduling change, inverter write, TOU/battery change, or Shine
  capture restart.

The read-side production upgrade can proceed only after the four disposition
preconditions at the start of this report are reviewed and satisfied.
