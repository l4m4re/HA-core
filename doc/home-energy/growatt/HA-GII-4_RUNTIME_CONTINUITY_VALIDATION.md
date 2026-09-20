# HA-GII-4 runtime and continuity validation

Disposition: **`HA_GII_RUNTIME_VALIDATION_ACCEPTED_WITH_FOLLOW_UP`**

This report records a bounded, read-only comparison of the reconciled
Home Assistant consumer with the live MIN/TL-XH + ARK installation. It is an
evidence gate, not a runtime or transport change.

## Baseline and scope

| Item | Value |
| --- | --- |
| Canonical GII `main` | `f061c4aeeadeb06246aac6d4d0732da36fc6996d` |
| Consumer branch | `validation/ha-gii-runtime-continuity-20260911` |
| Consumer starting SHA | `313f980` (`integration/register-spec-consolidation-20260911`) |
| Broker source SHA | `ef325f0` (`fix/ha-dev-2b-forensics-20260906`) |
| Runtime broker image | `growatt-rtu-broker:ha-dev-3d-predictive-20260911c` |
| Validation path | DEV TCP `:5021`, unit 1 |
| Modbus operations | FC04 input-register reads only |
| Capture window | 2026-09-11 17:32:02.932–17:32:32.997 UTC |

The broker DEV endpoint was reachable and the existing serialized/arbitrated
path was used. No direct serial access was used, and no secondary process
bypassed the broker. Production HA continued to report successful Growatt
fetches during the validation window. Port `:5020` was not used, and neither
the production container nor the broker configuration was changed.

The complete probe and sniff capture were deliberately temporary. The
compact, identifying-information-free summary is
[`data/HA-GII-4_RUNTIME_EVIDENCE_SUMMARY.json`](data/HA-GII-4_RUNTIME_EVIDENCE_SUMMARY.json).

## Read-only block validation

The probe read the vendor-native input pages as complete blocks:

| FC04 start/count | Samples | Returned words | Errors | Duration |
| --- | ---: | --- | ---: | ---: |
| 3000/125 | 4 | 125 every time | 0 | 4.8–7.5 ms |
| 3125/125 | 4 | 125 every time | 0 | 4.9–6.7 ms |
| 3250/125 | 4 | 125 every time | 0 | 4.8–12.7 ms |

The blocks were sampled four times over approximately 30 seconds. This is
strong evidence that the native pages are accepted through DEV and decode
consistently in the observed operating state; it is not a claim that every
possible inverter state or long-term transport failure has been exhausted.

A separate single FC04 `0/125` read also completed and returned 125 words in
about 1.9 seconds. It yielded output power 559.7 and output-energy total
19622.6 kWh. An earlier bounded mixed-page attempt included one timeout on the
base page; that failed attempt is retained as transport context and is not
counted as a clean native-page success.

## Operating-state observations

The native-page samples represented a battery-discharge condition:

| Quantity | Register | Observed value |
| --- | ---: | ---: |
| PV/input power | I3001 | 126.3 W |
| AC output power | I3023 | 570.0 W |
| AC phase 1 power | I3028 | 570.2 W |
| Grid import | I3041 | 0.0 W |
| Grid export | I3043 | 0.0 W |
| House/load power | I3045 | 603.3 W |
| Battery voltage | I3169 | 212.76 V |
| Battery current | I3170 | +2.3 A under the current consumer interpretation |
| SOC | I3171 | 72% |
| Discharge power | I3178 | 474.0 W |
| Charge power | I3180 | 0.0 W |
| BMS battery current | I3217 | −2.2 A, signed `/100` |

The approximate balance 126.3 W PV + 474.0 W battery discharge = 600.3 W
against 603.3 W load is physically plausible, allowing for sampling and
conversion timing. Grid import and export were both zero in this sample.

## Evidence-gated fields

### I3170 battery current

I3170 and I3217 were captured together with voltage, SOC, charge/discharge
power, and the same native-page samples. In the observed discharge condition,
I3170 was +2.3 A while I3217 was −2.2 A. An earlier natural sample showed
approximately +1.7 A versus −1.8 A. This establishes a repeatable magnitude
correlation and opposite sign convention/measurement-point behavior, but it
does not establish that I3170 can never become negative: no charging or idle
condition was observed during this bounded run.

Conclusion: **`INSUFFICIENT_EVIDENCE`** for changing the consumer mapping.
Keep the accepted HA-GII-2 unsigned consumer interpretation pending a natural
charging/idle observation or stronger source evidence. Do not reinterpret the
two current registers as identical measurement points.

### I3101 real output power percentage

The raw value was 9 in all four samples and the runtime value was 9% (not a
negative wrapped value). A positive sample supports the existing HA unsigned
presentation, while it does not prove the full domain. The percentage is a
physically non-negative quantity in this use.

Conclusion: **`GII_FIX_SUPPORTED`** as a canonical metadata follow-up
candidate; **no HA change** is justified by this run. The canonical signedness
should be reviewed separately rather than silently changing the consumer.

### I3191, I3194, I3195 BMS scales

The repeated raw values were I3191=`0`, I3194=`2`, and I3195=`14`. Interpreting
them with the currently observed `/10` candidate gives 0.0, 0.2, and 1.4,
which are not sufficient to identify valid temperature semantics. The values
also look like unavailable or invalid channels in this state. No direct
vendor evidence or independent correlation resolves the scale.

Conclusion: **`INSUFFICIENT_EVIDENCE`**. All six consumer occurrences remain
unresolved; no scale change was made.

### I39

I39 was not promoted to a live-fix target. The native-page run does not provide
source-layout evidence for the outstanding I39 question, and adjacent words
were not combined into an inferred value.

Conclusion: **`GII_SOURCE_REVIEW_REQUIRED`**.

## Energy-counter continuity

The following values were observed without an artificial jump in the four
native-page samples:

| Counter | Register | Value |
| --- | ---: | ---: |
| Output/produced total | I55 | 19622.6 kWh |
| Energy to user total | I3069 | 7866.5 kWh |
| Energy to grid total | I3073 | 11169.8 kWh |
| Battery discharged total | I3127 | 3244.7 kWh |
| Battery charged total | I3131 | 3389.1 kWh |

The separate I55 reading agrees with the current live HA state for total
energy produced. Recent Recorder state tails for the selected cumulative
entities showed normal positive increments and no visible negative or giant
cutover jump. The current source registers and physical quantities were not
changed.

This bounded runtime evidence supports unsigned decoding and counter
continuity, but it is not a complete rollover/reset proof. The longer live
history also contains a small historical `-0.1` step for total produced energy,
and one pre-existing daily battery-discharge statistics aggregate is
implausibly large compared with its current state. No Recorder database was
edited. These observations prevent a full continuity sign-off for production.

## Live entity and statistics contract

A read-only inspection of the live HA registry/database found 94
`growatt_local` entities and 18 Growatt statistics metadata records. The
important cumulative entity IDs remain present, including:

- `sensor.growatt_total_energy_produced`
- `sensor.growatt_energy_to_grid_total`
- `sensor.growatt_energy_to_user_total`
- `sensor.growatt_battery_charged_total`
- `sensor.growatt_battery_discharged_total`

All 18 inspected statistics records have sum metadata; the energy records use
kWh and the running-hours record uses h. Unique IDs were inspected in the
live registry with identifying portions redacted. This confirms the public
surface exists, but a deployment cutover was not performed, so before/after
identity continuity still needs to be checked during the controlled
development-HA deployment.

## Additional presentation checks

- `power_to_user` at I3041, `power_to_grid` at I3043, and `power_user_load` at
  I3045 behaved consistently with import, export, and house-load semantics in
  the observed zero-grid-flow/discharge condition. This is supporting
  evidence, not a natural import/export sign test.
- I3021 decoded to 0.0 with the existing numeric conversion. The HA-GII-3
  change to `var`/`REACTIVE_POWER` is therefore presentation-only in this
  sample; the run did not deeply characterize reactive power.
- I3230=`3314` and I3231=`3311` decoded to 3.314 V and 3.311 V. These are
  physically plausible per-cell values and support the existing `/1000` scale.

## Sniff and audit evidence

The existing broker sniff analysis script was used; no new parser was added.
The bounded native capture contained 52 Shine request/response pairs, 104
cache-hit events, and 7 FC20 refreshes. It contained zero downstream
timeouts, physical-refresh failures, CRC errors, writes, or observed
asynchronous frames. The earlier failed mixed-page probe had two downstream
timeouts and one FC20 refresh failure and is kept separate from the clean
result.

The existing GII audit tooling was run against the extracted consumer map at
consumer SHA `313f980`: 299 mapping occurrences were checked, with 275
matches, 6 live-validation findings, 11 semantic mismatches, 3 signedness
mismatches, 3 unit mismatches, and 1 length mismatch. Required-action counts
were 275 `NO_HA_CHANGE`, 12 `GII_FOLLOW_UP_REQUIRED`, 6
`NEEDS_MORE_EVIDENCE`, 4 `DECODE_FIX_REQUIRED`, and 2
`SAFE_METADATA_FIX`; these are the reconciled audit inventory, not new live
changes.

## Tests

- HA-GII-2 decoder regressions: **8 passed**.
- Full consumer suite: **81 passed, 1 failed, 1 error, 1 warning**.
- The remaining failure and error are the known PyModbus simulator fixture
  incompatibility: the simulator constructs `SimData(address=-1)` under the
  installed PyModbus version. They occur in
  `test_growatt_api_read_write` and the `test_sensor_setup` fixture, before
  integration behavior is exercised.

## Follow-up and deployment boundary

The reconciled read-side consumer is broadly supported by the DEV runtime
evidence, but the following remain explicit follow-up gates:

1. Observe I3170 during a naturally occurring charging or near-idle state.
2. Resolve I3191/I3194/I3195 only with direct evidence or repeated
   independent correlation.
3. Review the I3101 canonical signedness metadata separately.
4. Investigate the pre-existing Recorder statistics anomaly and perform a
   before/after entity/unique-ID/state/unit/statistics comparison during the
   controlled development-HA deployment.
5. Revisit I39 only with source-layout evidence.

No consumer code, broker configuration, production HA container, inverter
state, or Recorder data was changed by HA-GII-4. The next stage, if approved,
is a controlled development-HA deployment against DEV `:5021`; production
deployment and all write/control work remain outside this task.
