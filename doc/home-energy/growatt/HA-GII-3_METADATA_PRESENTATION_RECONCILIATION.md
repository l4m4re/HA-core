# HA-GII-3 metadata and presentation reconciliation

## Disposition

`HA_GII_METADATA_RECONCILIATION_ACCEPTED_WITH_FOLLOW_UP`

The high-confidence presentation corrections are implemented without changing
register selection, decoding, entity keys, unique IDs, polling, writes, or the
broker. Canonical and runtime evidence is still incomplete for several
registers, so this is not a complete semantic reconciliation.

## Baseline and evidence

- Consumer starting branch: `integration/register-spec-consolidation-20260911`
- Consumer starting SHA: `4cdf2c9` (`Merge HA-GII-2 bounded read decoder corrections`)
- HA-GII-2 ancestry: verified; `5cb60ac` is an ancestor of the starting SHA.
- Canonical GII `main`: `f061c4aeeadeb06246aac6d4d0732da36fc6996d`
- Audit mode: `mapping_declared`, which models the accepted HA-GII-2
  decoder behavior rather than the historical always-signed model.
- Implementation commit: `217851e`
- Live validation: not used. No production HA, broker, inverter, or write
  operation was touched.

The only pre-existing untracked consumer material, `doc/growatt_web/`, was
preserved and is not part of this change.

## Audit regression

The corrected audit was run against an extracted consumer snapshot before and
after the metadata changes. The snapshot was temporary and is not committed.

| Metric | Before | After |
| --- | ---: | ---: |
| mapping occurrences checked | 299 | 299 |
| unique family/table/address mappings | 230 | 230 |
| findings | 22 | 20 |
| MATCH | 273 | 275 |
| UNIT_MISMATCH | 5 | 3 |
| SEMANTIC_MISMATCH | 11 | 11 |
| SIGNEDNESS_MISMATCH | 3 | 3 |
| LENGTH_MISMATCH | 1 | 1 |
| NEEDS_LIVE_VALIDATION | 6 | 6 |

The two reactive-power occurrences at I234 and I3021 are resolved by the
shared HA descriptor. The audit continues to report the unrelated
signedness, length, semantic, and live-evidence findings; none disappeared by
changing the audit model or source mapping.

## Implemented corrections

### I234 and I3021 reactive power

The existing `output_reactive_power` entity remains the same entity and uses
the same physical source(s). Its metadata is now:

- unit: `W` → `var`
- device class: `POWER` → `REACTIVE_POWER`
- state class: unchanged measurement
- I3021 register: unchanged, two words, signed, scale 10
- field key and unique-ID template: unchanged

Home Assistant provides `UnitOfReactivePower.VOLT_AMPERE_REACTIVE` and the
`REACTIVE_POWER` device class, so retaining `POWER` with `var` would have
violated the current entity metadata rules. The value and sign behavior are
unchanged; the regression test decodes the same signed raw value as `-1000.0`.

This is an instantaneous measurement, not a cumulative energy counter. The
entity ID and unique ID remain continuous, and no long-term-statistics source
is involved. Recorder history before the cutover was recorded with the old W
metadata; consumers should treat the unit boundary as a metadata boundary,
not as a physical value conversion.

### I3230 and I3231 cell voltage presentation

The BMS maximum/minimum cell-voltage descriptors now use
`suggested_display_precision=3`.

- source registers: unchanged, I3230/I3231
- decoder: unchanged, unsigned `/1000 V`
- example values: unchanged, `3314` → `3.314 V` and `3311` → `3.311 V`
- voltage unit and device class: unchanged
- entity IDs and unique IDs: unchanged

This only prevents the frontend from hiding meaningful millivolt precision;
it does not invent precision or rescale the source.

### I3101 real output power percentage

The field remains `real_output_power_percent`, remains a percentage, and keeps
its register, length, scale, unsigned runtime decoder behavior, key, and unique
ID. The incorrect `POWER_FACTOR` device class was removed. Home Assistant has
no generic “output percentage” device class; `POWER_FACTOR` describes a
different ratio and is therefore not contract-correct for this quantity.

The accepted HA-GII-2 decoder audit still reports the independent signedness
mismatch at I3101. Decoder behavior was explicitly out of scope here and was
not changed.

## Review of every post-HA-GII-2 unit mismatch

The classification names below are the HA-GII-3 review categories.

| Register | HA field | Finding | Classification | Action |
| --- | --- | --- | --- | --- |
| I234 | `output_reactive_power` | `W` vs `var` | `HA_METADATA_FIX` | corrected through shared descriptor |
| I3021 | `output_reactive_power` | `W` vs `var` | `HA_METADATA_FIX` | corrected to `var` + reactive-power class |
| I3032 | `output_2_power` | `W` vs canonical `VA` | `GII_CANONICAL_FOLLOW_UP` | unchanged; source/canonical presentation is still qualified |
| I3036 | `output_3_power` | `W` vs canonical `VA` | `GII_CANONICAL_FOLLOW_UP` | unchanged; source/canonical presentation is still qualified |
| I1014 | `soc` | `%` vs malformed canonical `lith/leadacid` | `GII_CANONICAL_FOLLOW_UP` | unchanged; canonical unit is not credible evidence |

I3032 and I3036 are not mechanically changed to VA: the canonical entries are
`resolved_with_notes`, while the existing HA fields describe phase output
wattage and the independent comparison material records a W-versus-VA
conflict. I1014 remains the normal HA percentage/battery presentation pending
canonical correction.

## Review of every post-HA-GII-2 semantic mismatch

| Register | HA field | Canonical semantic label | Classification | Action |
| --- | --- | --- | --- | --- |
| I73 | `input_4_energy_total` | `pv.mppt4.energy_total` | `VALID_LEGACY_ALIAS` | unchanged; same PV4 total-energy quantity |
| I1021 | `pac_to_user_total` | `field.pactousertotalh` | `GII_CANONICAL_FOLLOW_UP` | unchanged |
| I1029 | `pac_to_grid_total` | `field.pac_to_grid_total` | `GII_CANONICAL_FOLLOW_UP` | unchanged |
| I1044 | `energy_to_user_today` | `field.etouser_todayh` | `GII_CANONICAL_FOLLOW_UP` | unchanged |
| I1046 | `energy_to_user_total` | `field.etouser_totalh` | `GII_CANONICAL_FOLLOW_UP` | unchanged |
| I1048 | `energy_to_grid_today` | `field.etogrid_todayh` | `GII_CANONICAL_FOLLOW_UP` | unchanged |
| I1050 | `energy_to_grid_total` | `field.etogrid_totalh` | `GII_CANONICAL_FOLLOW_UP` | unchanged |
| I1052 | `discharge_energy_today` | `field.edischarge1_toda_yh` | `GII_CANONICAL_FOLLOW_UP` | unchanged |
| I1054 | `discharge_energy_total` | `field.edischarge1_total_h` | `GII_CANONICAL_FOLLOW_UP` | unchanged |
| I1056 | `charge_energy_today` | `field.echarge1_todayh` | `GII_CANONICAL_FOLLOW_UP` | unchanged |
| I1058 | `charge_energy_total` | `field.echarge1_totalh` | `GII_CANONICAL_FOLLOW_UP` | unchanged |

The ten storage entries are recognizable HA quantity names, but the current
canonical semantic keys are source-field labels (including “high word”) and
are not yet normalized enough to justify renaming or changing any existing
Energy-dashboard entity. All cumulative entities therefore retain their
existing source, unit, state class, counter meaning, and unique ID.

## Explicitly deferred findings

- I39 remains the known read-length/source-layout follow-up.
- I3170 remains the live sign/measurement-point follow-up and was not
  conflated with I3217.
- I3101's canonical signedness mismatch remains separate from the metadata
  correction.
- The six live-validation occurrences are the two consumers each of I3191,
  I3194, and I3195; their BMS scale evidence remains unresolved.
- The I3032/I3036 VA-versus-W presentation and I1014 canonical SOC unit need
  canonical/source review.
- No energy source migration or cumulative-counter change was made.

## Contract and scope check

The patch changes only sensor descriptors and adds regression tests/documentation.
No register address, table, read length, scale, signedness, field key, unique-ID
template, polling cadence, write path, or broker configuration changed. No
replacement entities were created. The reactive-power unit change is the only
Recorder-visible metadata boundary; it preserves the physical quantity and
entity identity, but old history should not be interpreted as if its unit
metadata were retroactively rewritten.

## Validation

- Focused HA-GII-2 + HA-GII-3 tests: **8 passed**.
- Full consumer test suite: **81 passed, 1 failed, 1 error, 1 warning**.
- The failure and error are pre-existing environment incompatibilities in the
  shared broker simulator's PyModbus `SimData(address=-1)` construction and
  the sensor setup fixture's HA test-package mix; they are outside this patch.
- `python3 -m compileall -q custom_components tests`: passed.
- `git diff --check`: passed.
- Ruff's new-file import-order check: passed. A repository-wide/changed-file
  Ruff invocation also reports pre-existing repository style findings in the
  older integration files (namespace-package, legacy imports, and existing
  `__future__` usage); those files were not reformatted as part of this bounded
  task.

The next stage remains separate: read-only runtime and continuity validation
through DEV `:5021`, including I3170, I39, instantaneous equivalence, and
cumulative-energy continuity.
