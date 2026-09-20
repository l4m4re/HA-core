# HA-GII-4A — OpenAPI token reauthorization and V4 cross-validation

Disposition: **`HA_GII_CLOUD_VALIDATION_ACCEPTED_WITH_FOLLOW_UP`**

This addendum follows the earlier HA-GII-4A run with the reactivated token and
the V4 API family. It is read-only evidence. No HA, GII, broker, inverter, or
production configuration was changed.

The sanitized machine-readable evidence is in
[`data/HA-GII-4A_OPENAPI_REAUTH_V4_EVIDENCE.json`](data/HA-GII-4A_OPENAPI_REAUTH_V4_EVIDENCE.json).

## Client and authorization result

The exact requested package was installed in a temporary Python 3.13
environment: `growatt-public-api 2026.5.19`. The prior V1 client remains
`growattServer 2.2.0 / OpenApiV1`. The token was used only at runtime and is
not present in this report or evidence.

| API/read | Result | Previous HA-GII-4A result |
| --- | --- | --- |
| V4 `POST /v4/new-api/queryDeviceList` | `200`, `error_code 0`; one MIN device authorized | not previously attempted |
| V4 `Min.details_v4()` | `200`, `error_code 0`; `data.devices` | not previously attempted |
| V4 `Min.device_info()` | `200`, `error_code 0`; device type/model and nominal power | not previously attempted |
| V4 `Min.power_realtime()` | `200`, `error_code 0`, `data=null` | not previously attempted |
| V4 `Min.energy_v4()` | `200`, `error_code 0`; rich `data.devices` payload | not previously attempted |
| V4 `Min.energy_history_v4()` | `200`, `error_code 0`; 145 samples | not previously attempted |
| V1 `device/list` | `200`, `error_code 0` | `10012` rate limit |
| V1 MIN detail | `200`, `error_code 0` | `10011` permission denied |
| V1 MIN current energy | `200`, `error_code 0` | not available with the old token |
| V1 `plant/power` | `200`, `error_code 0`; 288 records | `10011` permission denied |

The authorization behavior changed materially. The old token’s `10011` result
was not a permanent account-scope limitation: the reactivated token authorizes
both V1 device data and the V4 MIN data family. The earlier V1 `10012` was a
rate-limit event, not evidence that device-list authorization was absent.

No write/configuration endpoint was called. In particular, no setting, time,
schedule, export, charge/discharge, firmware, or inverter-control method was
used.

## V4 endpoint field inventory

The successful V4 response envelopes expose `data`, `error_code`, and
`error_msg`. The useful payload shapes are:

* `queryDeviceList`: `count`, `data`, paging fields and `last_pager`.
* `details_v4`: `devices`, including model, status, power, energy summary,
  address, communication and battery metadata.
* `device_info`: `device_type`, `device_model`, `datalogger_model`,
  `nominal_power`, battery-capacity/model fields and `has_battery`.
* `energy_v4`: `devices`, including PV/AC power, grid/load values, BDC1/BMS
  current, voltage, SOC, temperatures, status and cumulative counters.
* `energy_history_v4`: `datas`, `have_next`, and `start`; 145 detailed records
  were returned for the bounded one-day request.
* `power_realtime`: successful envelope but `data=null`, so it contributed no
  independent high-frequency values.

## Timestamped V4 versus Modbus sample

The V4 energy sample was timestamped `2026-09-11 21:42:22` in the cloud’s
local wall-clock representation. The immediately following local sample was
at approximately `2026-09-11 19:38:01 UTC` (21:38 CEST), through DEV `:5021`,
using complete FC04 pages `3000/125`, `3125/125`, and `3250/125`.

| Semantic quantity | V4 field/value | Local register/value | Classification |
| --- | --- | --- | --- |
| PV power | `ppv` = 0.0 W | I3001 = 0.0 W | `AGREE` |
| AC output | `pac` = 608.4 W | I3023 = 606.7 W | `AGREE_WITH_CLOUD_LATENCY` |
| House load | `pac_to_local_load` = 641.0 W | I3045 = 641.0 W | `AGREE` |
| Grid import/export | `power_of_grid_take/feed` = 0.0/0.0 W | I3041/I3043 = 0.0/0.0 W | `AGREE` in zero-flow state |
| SOC | `bdc1_soc`/`bms_soc` = 59% | I3171 = 59% | `AGREE` |
| Battery voltage | `bdc1_vbat`/`bms_vbat` = 210.12/210.40 V | I3169 = 210.14 V | `AGREE_WITH_CLOUD_LATENCY`; BDC/BMS measurement points remain distinct |
| BDC battery current | `bdc1_ibat` = +3.0 A | I3170 = +2.9 A | `AGREE_WITH_CLOUD_LATENCY` |
| BMS battery current | `bms_ibat` = −3.1 A | I3217 = −2.9 A | `AGREE_WITH_CLOUD_LATENCY` |
| Discharge/charge power | `bdc1_discharge/charge_power` = 647.0/0.0 W | I3178/I3180 = 617.0/0.0 W | `AGREE_WITH_CLOUD_LATENCY` |
| Real output percentage | `real_op_percent` = 10% | I3101 = 10% | `AGREE` |

The current comparison independently supports the existing distinction between
I3170 and I3217: the cloud exposes the same positive BDC-side current and
negative BMS-side current pattern, rather than treating them as one register
with a simple sign error.

## BMS, cell and energy findings

The V4 API exposes BMS SOC, SOH, voltage, current, status and temperature
fields. It does not expose a defensible direct equivalent of I3191/I3194/I3195;
the returned BMS/BDC temperature fields cannot be assigned to those three
physical registers without additional evidence. Their local scale remains
unresolved.

The V4 model did not provide usable maximum/minimum cell-voltage fields in the
returned MIN energy records. I3230/I3231 therefore remain `NO_CLOUD_EQUIVALENT`;
the local 3.275/3.270 V values are not contradicted. Numerically similar
`bdc2_*` fields are not reinterpreted as cell voltages without evidence.

Cumulative counters provide strong independent support:

| Quantity | V4 field | V4 | Local register | Local |
| --- | --- | ---: | --- | ---: |
| Energy to user total | `e_to_user_total` | 7866.5 kWh | I3069 | 7866.5 kWh |
| Energy to grid total | `e_to_grid_total` | 11169.8 kWh | I3073 | 11169.8 kWh |
| Battery charge total | `e_charge_total` | 3389.1 kWh | I3131 | 3389.1 kWh |
| Battery discharge total | `e_discharge_total` | 3246.1 kWh | I3127 | 3246.1 kWh |
| AC generated total | `eac_total` | 19623.9 kWh | I55 | 19623.3 kWh in prior local/HA evidence |

V4 history repeats these relationships at five-minute points around 21:32,
21:37, 21:42 and 21:47. The V1 current-energy repeat after the V4 calls
returned the same 21:47 values, including `pac=627.3`, `bdc1_ibat=3.1`,
`bms_ibat=-3.2`, `e_to_user_total=7866.5`, `e_to_grid_total=11169.8`, and
the battery totals. V1 plant power independently returned 607.5 W at 21:35,
608.4 W at 21:40, and 627.3 W at 21:45.

## Cloud endpoint semantics requiring caution

Two cloud metadata inconsistencies are now visible:

1. `device_info()` reports `has_battery=false` and zero battery capacity even
   though `energy_v4()` and history return populated ARK/BDC/BMS values and
   the local device is demonstrably a MIN/TL-XH battery installation.
2. `details_v4()` reports `status_text=tlx.status.checking` with zero summary
   power/energy, while `energy_v4()` reports `status_text=Normal` with current
   values. Its ISO and display timestamp fields also use inconsistent timezone
   representations. These are cloud endpoint freshness/metadata differences,
   not reasons to alter Modbus semantics.

Therefore cloud field names are useful semantic corroboration, but the local
physical register identity remains canonical. The cloud output does not justify
changing HA mappings or GII data in this task.

## Disposition

The reactivated token changes the previous authorization conclusion: the
Growatt cloud now provides strong independent read-side support for I3170,
I3217, SOC, voltage, power, grid/load zero-flow semantics, I3101 and all major
cumulative energy counters. I3191/I3194/I3195 and I3230/I3231 remain bounded
follow-up items because the V4 cloud model does not expose defensible direct
equivalents.

Final disposition: **`HA_GII_CLOUD_VALIDATION_ACCEPTED_WITH_FOLLOW_UP`**.
