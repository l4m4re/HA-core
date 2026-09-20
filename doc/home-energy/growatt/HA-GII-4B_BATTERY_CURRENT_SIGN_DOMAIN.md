# HA-GII-4B — Battery-current sign domain

Disposition: **`HA_GII_BATTERY_CURRENT_SIGN_RESOLVED`**

This is a bounded, read-only follow-up to HA-GII-4A. It resolves the observed
sign domain of the MIN/TL-XH BDC and BMS battery-current fields using natural
charging and discharging records. It does not change the Home Assistant
consumer, canonical GII data, broker behavior, inverter state, or production
Home Assistant.

## Baseline and scope

| Item | Value |
| --- | --- |
| Branch | `validation/ha-gii-battery-current-sign-20260911` |
| Starting SHA | `4a452777ea1b8a8d596534723a476ecc42810afd` |
| Evidence commit SHA | `f3a6113d98cae2c07a26e8552583c783a2cd77bc` |
| Source | Existing temporary V4 `energy_history_v4()` response |
| Client | `growatt-public-api 2026.5.19` |
| History coverage | One-day response, 145 records dated 2026-09-11 |
| Writes | None |
| Runtime/configuration changes | None |

The already available one-day V4 history was sufficient, so no additional
cloud request was needed. The raw response remained temporary and is not
included in this repository. The timestamp strings below are reproduced as
returned by the API; their timezone is not asserted.

Records were classified conservatively:

* **Charging:** `bdc1_charge_power > 0` and `bdc1_discharge_power == 0`.
* **Discharging:** `bdc1_discharge_power > 0` and `bdc1_charge_power == 0`.

This produced 66 charging records and 77 discharging records. The power
direction and BMS status provide stronger operating-state evidence than a
current value alone. The charging population had BDC/BMS SOC values from 62%
to 90%; the sampled sequences show SOC increasing or holding while charge
power is positive, including the expected hold at high SOC.

## Representative history records

The API fields `bdc1_ibat` and `bms_ibat` are shown in amperes as returned by
the V4 client. BDC and BMS voltages, power, and SOC are included to retain the
operating context.

| API timestamp | State | BDC current (A) | BMS current (A) | BDC V (V) | BMS V (V) | Charge (W) | Discharge (W) | SOC BDC/BMS | BMS status | Real OP % |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| 2026-09-11T09:22:56 | charge | +2.2 | +2.2 | 213.45 | 213.8 | 464 | 0 | 62/62 | 1 | 6 |
| 2026-09-11T09:32:57 | charge | +2.9 | +2.8 | 214.15 | 214.3 | 620 | 0 | 63/63 | 1 | 6 |
| 2026-09-11T14:59:02 | discharge | +0.6 | −0.5 | 213.26 | 213.4 | 0 | 130 | 83/83 | 2 | 11 |
| 2026-09-11T15:04:02 | charge | +1.1 | +1.1 | 213.91 | 214.1 | 247 | 0 | 83/83 | 1 | 10 |
| 2026-09-11T16:11:16 | discharge | +9.6 | −9.7 | 211.27 | 211.5 | 0 | 2035 | 78/78 | 2 | 41 |
| 2026-09-11T16:16:16 | charge | +0.9 | +1.0 | 213.63 | 213.8 | 213 | 0 | 78/78 | 1 | 9 |
| 2026-09-11T18:21:18 | discharge | +0.6 | −0.6 | 213.42 | 213.6 | 0 | 144 | 76/76 | 2 | 11 |
| 2026-09-11T18:26:18 | charge | +1.2 | +1.2 | 214.02 | 214.3 | 265 | 0 | 76/76 | 1 | 11 |

The transitions are particularly useful because the two current fields change
in opposite ways without changing the physical source register:

* at 16:11 the inverter was discharging: BDC `+9.6 A`, BMS `−9.7 A`;
  five minutes later it was charging: BDC `+0.9 A`, BMS `+1.0 A`;
* at 18:21 it was discharging: BDC `+0.6 A`, BMS `−0.6 A`; at 18:26 it was
  charging: BDC `+1.2 A`, BMS `+1.2 A`.

## Sign-count result

| Classified state | Records | BDC `bdc1_ibat` negative / zero / positive | BMS `bms_ibat` negative / zero / positive |
| --- | ---: | ---: | ---: |
| Charging | 66 | 0 / 3 / 63 | 0 / 9 / 57 |
| Discharging | 77 | 0 / 2 / 75 | 74 / 3 / 0 |

No negative `bdc1_ibat` value occurred in either operating direction. The
positive BDC current is therefore a current magnitude (or otherwise a
non-negative BDC-side quantity) in this observed MIN/TL-XH history domain.
The BMS current is directional: it is negative during discharge and positive
during charge. This confirms that the two cloud fields are distinct BDC-side
and BMS-side measurements, rather than one incorrectly signed copy.

One discharging record contained an implausible battery-voltage outlier around
2130 V. It is unrelated to the current sign counts and was not used as
semantic evidence. The remaining voltage values are in the expected roughly
210–218 V range.

## I3170 / I3217 consequences

The current canonical MIN/TL-XH entry is:

* I3170 / `bdc1_ibat`: `s16 / 10 A`, `signed: true`, preferred
  `battery_current`;
* I3217 / `bms_ibat`: `s16 / 100 A`, signed, alternate `battery_current`.

The current GII signedness for I3170 is not supported by this larger natural
history sample. A future bounded canonical correction should represent I3170
as an unsigned/non-negative magnitude with `/10 A` scaling, or use an explicit
metadata form that states “non-negative BDC current magnitude”. This report
does **not** apply that correction.

The existing HA interpretation of I3170 as a positive battery-current value is
correct for the observed runtime domain. No entity migration, sign inversion,
unique-ID change, or Energy-dashboard change is indicated. I3217 should remain
available as the signed BMS-side current and must not be collapsed into I3170.

This resolves the practical sign question across naturally observed charge and
discharge states. It does not claim a formal firmware guarantee for every
unobserved fault or diagnostic state; such a state would require separate
evidence before changing the interpretation.

## I3101 follow-up

`real_op_percent` was non-negative in all 145 V4 history records:

| Sample count | Minimum | Maximum | Negative | Zero |
| ---: | ---: | ---: | ---: | ---: |
| 145 | 0% | 43% | 0 | 1 |

This is consistent with a non-negative output-power percentage and supports a
canonical GII metadata defect finding: the current I3101 entry is marked
signed even though the vendor range and all observed V4 values are
non-negative. The recommended follow-up is unsigned/non-negative percentage
metadata. No GII or HA change is made here, and I3101 is not changed at
runtime.

## Final disposition

**`HA_GII_BATTERY_CURRENT_SIGN_RESOLVED`**

The bounded natural-history evidence found charging records and establishes:

* BDC/I3170 is non-negative in both discharge and charge records;
* BMS/I3217 is negative during discharge and positive during charge;
* I3170 should not be treated as a signed direction value;
* current HA I3170 presentation is correct, while the canonical GII signedness
  should be corrected in a later reviewed change;
* I3101 signedness is a separate canonical metadata defect candidate;
* no inverter write, broker change, HA change, production change, or
  configuration change was made.

The final branch-head SHA is supplied in the handoff after this report-only
commit. HA-GII-5 is not started by this task.

The compact sanitized evidence is available at
[`data/HA-GII-4B_BATTERY_CURRENT_SIGN_EVIDENCE.json`](data/HA-GII-4B_BATTERY_CURRENT_SIGN_EVIDENCE.json).
