# HA-GII-5 — controlled development Home Assistant deployment validation

Disposition: **`HA_GII_DEV_DEPLOYMENT_ACCEPTED_WITH_FOLLOW_UP`**

This is a bounded, read-only development deployment against the real
MIN 6000TL-XH + ARK installation. Production Home Assistant, the live broker
configuration, the inverter, the ARK and the Shine were not changed.

## Reproducibility and boundaries

| Item | Value |
| --- | --- |
| HA consumer branch | `integration/register-spec-consolidation-20260911` |
| HA consumer SHA | `1409300467e5fe2ce48124b6f0516574f2d3189a` |
| Canonical GII branch | `main` |
| Canonical GII SHA | `5fa71e87ac89f66b13dcf1599834a2f7a446981b` |
| HA Core SHA | `1f3748d9310fad0a9b22ceec17654fcb8d42069f` |
| HA Core version | `2026.9.0` |
| Development endpoint | `192.168.1.148:5021`, unit 1 |
| Production endpoint | not used by development HA (`:5020` remained in production) |
| Dev poll interval | 5 seconds |
| Dev process | temporary HA process, stopped after the bounded run |
| Modbus access | broker-mediated TCP only; no serial device was opened |

The development config entry already contained the required TCP endpoint; no
dev configuration file was changed for this validation. Its model was
`MIN 6000TL-XH`, type `hybrid_120_TL_XH`, unit 1, and power control was false.
No FC06, FC10/0x10 or other write operation was issued by development HA.

## Source loading proof

The loaded integration path was the workspace symlink
`config/custom_components/growatt_local` pointing to
`external/Homeassistant-Growatt-Local-Modbus/custom_components/growatt_local`.
The manifest version was `0.2.1`; the manifest SHA-256 was identical through
both paths. A filesystem search found only the checked-out source directory
and that intended symlink, with no copied `custom_components/growatt_local`
tree shadowing it.

The runtime source was inspected directly. In particular, the actual source
contains the accepted `signed=True` declarations for I3021, I3041, I3043,
I3045, I3178 and I3180. The older checked-in GII input snapshot omits those
flags and was not treated as authoritative for this deployment.

## Startup and entity contract

Development HA started successfully and initialized the Growatt config entry.
There was no traceback, setup retry loop, duplicate-entity startup error, or
invalid device-class/unit error. The disposable development Recorder opened
and accepted new states.

The dev entity registry contained 95 Growatt entries and 94 distinct unique
IDs. One pre-existing unique-ID collision is present between the existing
sensor and switch for `ac_charge_enabled`; both entries predate this run and
no new entity identity was created by the deployment. The runtime state table
contained 93 entries for the selected prefix. No entity IDs or unique IDs were
renamed.

Representative public identities remained stable, including:

| Quantity | Entity ID suffix | Unique ID suffix |
| --- | --- | --- |
| output power | `output_power` | `output_power` |
| reactive power | `reactive_wattage` | `output_reactive_power` |
| battery current (BDC) | `battery_current` | `battery_current` |
| BMS current | `bms_battery_current` | `bms_battery_current` |
| total generated energy | `total_energy_produced` | `output_energy_total` |
| battery charged total | `battery_charged_total` | `charge_energy_total` |
| battery discharged total | `battery_discharged_total` | `discharge_energy_total` |

## Presentation and decoded values

The following near-synchronous comparison uses the final physical FC04
responses in the sniff capture and the development HA states. Values are
decoded with the current consumer map.

| Register | Broker raw/decode | Dev HA state | Classification |
| ---: | --- | --- | --- |
| I3001 | `0` → `0.0 W` | `0.0 W` | `AGREE` |
| I3023 | `4285` → `428.5 W` | `428.5 W` | `AGREE` |
| I3021 | `0` → `0.0 var` | `0.0 var`, reactive-power class | `AGREE` |
| I3041 | `0` → `0.0 W` | `0.0 W` | `AGREE` |
| I3043 | `0` → `0.0 W` | `0.0 W` | `AGREE` |
| I3045 | `4640` → `464.0 W` | `464.0 W` | `AGREE` |
| I3101 | `7` → `7 %` | `7 %` | `AGREE` |
| I3169 | `20999` → `209.99 V` | `209.99 V` | `AGREE` |
| I3170 | `21` → `+2.1 A` | `+2.1 A` | `AGREE` |
| I3171 | `49` → `49 %` | `49 %` | `AGREE` |
| I3178 | `4660` → `466.0 W` | `466.0 W` | `AGREE` |
| I3180 | `0` → `0.0 W` | `0.0 W` | `AGREE` |
| I3217 | `0xff34` → `-2.2 A` (`/100`, signed) | `-2.2 A` | `AGREE` |
| I3230 | `3271` → `3.271 V` | `3.271 V` | `AGREE` |
| I3231 | `3268` → `3.268 V` | `3.268 V` | `AGREE` |

The same physical page contained stable cumulative values: I3049=`11.3 kWh`
today, I3051=`19624.8 kWh` generated total, I3069=`7866.5 kWh` to user,
I3073=`11169.8 kWh` to grid, I3127=`3247.1 kWh` discharged total and
I3131=`3389.1 kWh` charged total. No artificial jump was introduced during
the bounded run. I3170 remained a non-negative BDC/storage-device magnitude,
while I3217 remained the separately signed BMS current; the two were not
collapsed.

I3021 was exposed as `var` with the reactive-power device class. I3230/I3231
retained millivolt-scale precision. I3101 remained a non-negative percentage
without a power-factor class. The current signed I3178/I3180 behavior produced
plausible ordinary positive/zero values; their independent physical
signedness remains deferred as required.

## Runtime read plan and broker capture

The static MIN/TL-XH native plan remains:

| Cadence | Blocks |
| --- | --- |
| fast | FC04 input 3000/125 and 3125/125 |
| control | FC03 holding 3000/125 |
| static | FC03 holding 0/125 |
| diagnostic | FC04 input 3250/125 |

The bounded capture was `/tmp/growatt-ha-gii5-20260911-211609.jsonl` and was
analysed with the existing `tools/analyze_sniff_log.py`; no new parser was
created. The capture covered 2026-09-11 21:16:10.042–21:21:24.257 UTC
(5m14.215s). The dev HA window was 21:16:18.732–21:21:18.295 UTC.

During the dev window there were exactly 183 DEV_TCP cache hits:

| Function | Start/count | Requests | Physical dev reads |
| ---: | --- | ---: | ---: |
| FC03 | 3000/125 | 61 | 0 |
| FC04 | 3000/125 | 61 | 0 |
| FC04 | 3125/125 | 61 | 0 |

There were no DEV base-page requests, no one-register-per-entity reads and no
DEV cache misses. Cache age ranged from 0.2s to 177.1s, which is within the
intended minutes-old HA tolerance. The complete block reads used to refresh
the cache were therefore independent broker work, not an accidental dev HA
polling storm.

The capture contained 1,537 JSONL records and 454,883 bytes. The existing
analyser reported:

* PREFETCH: 18 requests, 16 responses, 0 timeouts, 0 drops and 0 bad CRC;
* SHINE: 259 requests, 258 responses, two analyser timeout entries, one bad
  CRC entry and no drops;
* the two SHINE timeout entries represent one failed physical
  `GROWATT_FC0x20` refresh plus its source-less synthetic timeout record;
* `GROWATT_FC0x20` (function byte `0x20`, decimal 32) had 64 request frames
  and 62 response frames in the analyser's non-standard-function summary;
* one `fc20_refresh_failed` occurred at 21:17:46.048 UTC;
* no development-originated write frame was present;
* physical response CRCs were valid. The single bad-CRC record was the empty
  synthetic response associated with the Shine timeout;
* no asynchronous frame outside the broker's framed capture was observed.

The broker performed 16 physical refreshes during the capture (12
predictive, 4 background). The 20/15-word auxiliary refreshes completed in
about 52–53 ms. Native-page refreshes took about 1.4–3.96 s in this mixed
Shine/production run; a predictive FC03 0/125 refresh took 7.49 s and had to
retry. None of these refreshes failed. In particular, the slow base-page
operation was not requested by DEV_TCP and did not block a dev response,
because the three dev blocks were served from cache.

The separate long-running Shine capture that predated this bounded test was
left untouched. The bounded file is temporary and is not committed.

## Production coexistence

The production broker container remained running with restart count zero and
the same image identity `growatt-rtu-broker:ha-dev-3d-predictive-20260911c`.
Production traffic in the bounded capture comprised six cache-hit cycles for
each of its normal requests: FC03 0/1, FC03 3049/1, FC04 3164/68, FC04
3101/32 and FC04 3000/100. The production HA logs continued to report
successful Growatt fetches. In a subsequent 12-minute read-only log check
there were 12 successful fetches and zero Growatt errors, exceptions or
timeouts; the broker still had restart count zero.

The repeated production TCP connect/EOF lifecycle is the existing short-lived
`:5020` connection pattern, not evidence of dev starvation. No broker restart,
production configuration change, serial reconnect command or production HA
change was made.

## Recorder and statistics

The development Recorder created the expected metadata for energy and
measurement entities. The inspected cumulative state histories were
non-decreasing during the run:

* total generated energy: 2 samples, `19623.2` → `19624.8 kWh`;
* battery discharged total: 3 samples, `3245.3` → `3247.1 kWh`;
* battery charged total: 1 unchanged sample at `3389.1 kWh`;
* energy-to-user and energy-to-grid totals remained unchanged at
  `7866.5` and `11169.8 kWh`.

There are 27 Growatt `statistics_meta` rows in the disposable dev database.
The only relevant warning was the known historical metadata boundary:
reactive power is now `var`, while an older compiled statistics record still
has unit `W`. HA consequently suppressed new long-term statistics for that
entity until the unit returns to a compatible value. This is a pre-existing
statistics continuity issue from the accepted HA-GII-3 presentation change;
it was neither hidden nor repaired here. No statistics rows were edited.

The two known production-history anomalies remain outside this deployment:

1. The isolated approximately `-0.1 kWh` total-generated-energy step is a
   pre-existing bad/transient source sample (or old decoder sample), visible
   in the production state history before this run; it was not produced by the
   dev deployment.
2. The very large daily battery-discharge aggregate is a pre-existing
   Recorder aggregation artifact: the daily-resetting `*_discharged_today`
   quantity was historically accumulated as `total_increasing`. The raw state
   values remain ordinary (for example `7.6 kWh`) while the old statistic sum
   is approximately `144,776,692 kWh`. Production history was not modified.

These are cutover follow-ups, not evidence that the bounded dev deployment
changed a cumulative counter.

## Audit and tests

The canonical GII validators on GII `main` passed:

* canonical specification validator: OK, 4,048 records;
* resolved-reference validator: OK, 4,048 records, 60 live-read-verified,
  0 write-verified;
* MIN/TL-XH metadata validator: OK, no errors or warnings;
* GII test suite: 23 passed.

The current consumer audit was run in `mapping_declared` mode twice. Against
the historical snapshot, the result was 274 mapping occurrences with 11
`SIGNEDNESS_MISMATCH` findings, caused by the documented loss of signed flags
for I3021/I3041/I3043/I3045/I3178/I3180. A temporary corrected projection of
the actual accepted source produced:

* 274 occurrences;
* 249 `MATCH`;
* 0 `SIGNEDNESS_MISMATCH`;
* 3 `LENGTH_MISMATCH`;
* 5 `UNIT_MISMATCH`;
* 11 `SEMANTIC_MISMATCH`;
* 6 `NEEDS_LIVE_VALIDATION`.

The remaining findings are visible and unchanged follow-ups; the audit was
not weakened to make them disappear.

The focused and full consumer test runs both reached the same known external
simulator limitation:

* focused run: 36 passed, 1 failed and 1 error when the two simulator tests
  were included;
* full consumer suite: 81 passed, 1 failed, 1 error and 1 warning;
* excluding only `test_growatt_api_read_write` and `test_sensor_setup`: 81
  passed, 2 deselected and 1 existing socket warning.

Both failures occur before integration behavior is exercised because the
checked-out broker simulator passes address `0`, which the installed PyModbus
version converts to invalid `SimData(address=-1)`. This did not affect the
live broker or this read-only HIL run.

## Remaining follow-ups

The following remain intentionally unresolved and non-blocking for this gate:

* I39 physical layout;
* I1014 legacy SOC scale/unit;
* I3032/I3036 W versus VA;
* I3191/I3194/I3195 BMS temperature scale/channel identity;
* independent physical signedness proof for I3178/I3180;
* detailed `GROWATT_FC0x20` payload semantics;
* reactive-power long-term-statistics continuity across the `W` → `var`
  metadata boundary;
* the pre-existing `ac_charge_enabled` sensor/switch unique-ID collision;
* eventual investigation of the PyModbus simulator fixture incompatibility.

No production deployment, write-side control work, Recorder repair, entity
migration or broker modification was started. The next step is a separate
production-upgrade readiness review after these follow-ups have been reviewed.
