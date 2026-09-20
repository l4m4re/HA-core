# HA-GII-4A — Growatt cloud cross-validation

Disposition: **`HA_GII_CLOUD_VALIDATION_ACCEPTED_WITH_FOLLOW_UP`**

This is a bounded, read-only evidence task. It does not change the Home
Assistant consumer, GII canonical data, broker behavior, inverter state, or
production Home Assistant.

## Baselines

| Component | Baseline |
| --- | --- |
| Consumer starting SHA | `969553f03c7f78ad624d5362b89b2065c620b4bd` |
| Canonical GII `main` | `f061c4aeeadeb06246aac6d4d0732da36fc6996d` |
| Broker source | `ef325f00f6eb3ab3cc8b88b97844a7237fea02e4` |
| Broker image | `growatt-rtu-broker:ha-dev-3d-predictive-20260911c` |
| Local validation path | DEV TCP `:5021`, unit 1 |
| HA Core context | `2026.9.0`, SHA `1f3748d9310fad0a9b22ceec17654fcb8d42069f` |

The complete sanitized evidence is in
[`data/HA-GII-4A_GROWATT_CLOUD_EVIDENCE_SUMMARY.json`](data/HA-GII-4A_GROWATT_CLOUD_EVIDENCE_SUMMARY.json).

## API surface and access result

The existing `growattServer` package version 2.2.0 was used through its
token-based **Growatt OpenAPI V1** client. Only read operations were attempted.
The token was never written to a repository file or included in output.

The authorized plant-list response exposed one plant-level record with:

| Cloud field | Value | Interpretation | Confidence |
| --- | ---: | --- | --- |
| `current_power` | 578.7 W | plant current power; likely output for this single-device plant | LOW |
| `total_energy` | 19623.3 kWh | plant total generated energy | MEDIUM |

The response did not provide a measurement timestamp. It therefore cannot be
treated as a synchronized inverter sample.

The device-list route was initially rate-limited (`10012`, five-minute access
limitation). After the rate window, the MIN detail route returned
`error_permission_denied` (`10011`). Consequently, no authorized cloud fields
were obtained for battery, BMS, grid/load, cell, status, temperature, or
device-level energy counters. No write or configuration endpoint was called.

The package documents a plant-power route with five-minute samples. A separate
bounded plant-level read was attempted and also returned permission denied
(`10011`), so no historical samples were promoted into evidence.

## Local synchronized read

At `2026-09-11 19:07:42 UTC`, the local DEV endpoint returned all three
vendor-native FC04 pages (`3000/125`, `3125/125`, `3250/125`) with 125 words and
no errors. The selected values were:

| Quantity | Register | Value |
| --- | ---: | ---: |
| PV/input power | I3001 | 0.0 W |
| AC output power | I3023 | 728.9 W |
| Grid import/export | I3041/I3043 | 0.0 / 0.0 W |
| House/load power | I3045 | 770.0 W |
| Real output percentage | I3101 | 12% |
| SOC | I3171 | 63% |
| Battery voltage | I3169 | 210.4 V |
| I3170 battery current | I3170 | +3.6 A |
| BMS current | I3217 | −3.7 A |
| Discharge/charge power | I3178/I3180 | 770.0 / 0.0 W |
| BMS raw fields | I3191/I3194/I3195 | 0 / 2 / 13 |
| Cell max/min | I3230/I3231 | 3.283 / 3.271 V |
| Energy to user/grid total | I3069/I3073 | 7866.5 / 11169.8 kWh |
| Battery discharged/charged total | I3127/I3131 | 3245.7 / 3389.1 kWh |

A separate FC04 `0/125` probe timed out once. It is retained as transport
context only; it does not invalidate the successful native pages and is not
treated as a semantic cloud mismatch.

## Cloud-versus-local assessment

The cloud `current_power` (578.7 W) and the local I3023 value (728.9 W) cannot
be called a contradiction: the cloud response had no timestamp and is subject
to upload/aggregation latency. The comparison is **UNRESOLVED**, not a
sign-convention or scale finding.

The cloud `total_energy` value (19623.3 kWh) is in the same magnitude as the
existing local/HA I55 total-energy evidence. Because I55 was not included in
the exact synchronized native-page sample and the plant response had no
timestamp, this is recorded as **AGREE_WITH_CLOUD_LATENCY** with bounded
confidence, not as a new register proof.

The API response supplied no independent observations for:

* I3170 versus I3217 current convention;
* I3191/I3194/I3195 BMS temperature scale;
* I3101 signedness;
* grid import/export/load semantics;
* battery SOC, voltage, charge/discharge, BMS/SOH or temperatures;
* cell-voltage extrema;
* grid and battery energy counters.

These remain **INSUFFICIENT_EVIDENCE** or **NO_CLOUD_EQUIVALENT**. The local
sample itself continues to support the existing HA-GII-4 observations: I3170
and I3217 have similar magnitude and opposite sign in discharge; I3101 is a
non-negative runtime percentage; I3230/I3231 decode to physically plausible
millivolt cell voltages; and the native pages are stable.

## Implications for GII and HA

This cloud attempt provides limited independent support for the plant-level
output and total-generated-energy concepts, but no evidence that changes the
canonical physical register identity or decoder. It does not support changing
I3170, I3217, I3191/I3194/I3195, I3101, grid semantics, or cell-voltage scales.

No consumer defect was proven. No HA mapping, entity identity, unit, state
class, counter behavior, or statistics contract was changed. A future cloud
follow-up requires a token scope that authorizes MIN/TLX device detail and
history, or a separate export containing those fields. It should again be
read-only and rate-limit aware.

## Validation and disposition

The machine-readable artifact is sanitized and contains no account, device,
plant, private-network, or token identifiers. No production endpoint or
production HA instance was used or changed.

Validation results:

* HA-GII-2/3 regression tests: **8 passed**.
* Full consumer suite: **81 passed, 1 failed, 1 error, 1 warning**. The
  failure and error are the known PyModbus simulator incompatibility: the
  broker simulator constructs `SimData(address=-1)` under the installed
  PyModbus 3.13.1, before integration behavior is exercised. The warning is
  the existing blocked-socket warning in the config-flow test.
* `git diff --check`: clean.

Final disposition: **`HA_GII_CLOUD_VALIDATION_ACCEPTED_WITH_FOLLOW_UP`**.

The next implementation stage remains HA-GII-5 controlled development HA
deployment against broker DEV `:5021`; this evidence does not authorize runtime
or broker changes.
