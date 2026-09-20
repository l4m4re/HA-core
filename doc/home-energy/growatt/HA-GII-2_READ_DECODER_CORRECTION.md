# HA-GII-2 — bounded read-decoder correction

Disposition: `HA_GII_DECODER_FIX_ACCEPTED_WITH_FOLLOW_UP`

This change implements the first bounded read-side correction from HA-GII-1.
It does not change the broker, live Home Assistant configuration, inverter
state, write behavior, entity IDs, unique IDs, register sources, or Energy
Dashboard statistics configuration.

## Lineage

| Item | Value |
| --- | --- |
| Starting branch | `integration/register-spec-consolidation-20260911` |
| Starting commit | `ddfa899d171a2eb84cc9d78d2d1fe3c5a50171f2` |
| Canonical GII authority | `4296c596091bc118c953c69c39b8d625107fb083` |
| Working branch | `fix/ha-gii-read-decoder-20260911` |
| Implementation commit | `4fbb609c9ce576320edfd5be2c45e76a5116c659` |

## Exact implementation

`process_registers` now combines a two-word value as an unsigned 32-bit raw
value when `GrowattDeviceRegisters.signed` is false, and applies signed int32
conversion only when it is true. One-word integer and float behavior remains
unchanged.

The six known signed 32-bit TL-XH power mappings are explicitly marked
`signed=True`, preserving their existing signed engineering meaning:

- I3021 output reactive power;
- I3041 grid import power;
- I3043 grid export power;
- I3045 house load power;
- I3178 battery discharge power;
- I3180 battery charge power.

Unsigned two-word telemetry and energy mappings now use the declared unsigned
representation. Ordinary positive values are unchanged; high-bit values no
longer become negative merely because the old decoder always used signed
int32.

I110 and I3110 warning mappings now read exactly one word. I3110 remains the
raw `u16` inverter warning bitfield. I3111 remains an independent one-word
`present_fft_a` mapping and is not consumed as part of I3110. The warning
entity key and unique-ID construction are unchanged, but its value is now the
raw warning word rather than the old unsupported two-word interpretation.

## Deliberately deferred mappings

- I39 is unchanged. Its canonical two-word/source-layout description versus
  the one-word HA declaration requires a separate GII follow-up.
- I3170 remains unsigned in the mapping and is not conflated with signed BMS
  current I3217. It still needs live sign validation.
- I3101 remains unchanged; its signedness/percentage metadata needs a separate
  review.
- The six `NEEDS_MORE_EVIDENCE` occurrences remain unchanged: I3191, I3194,
  and I3195 occur in both relevant consumer surfaces because their canonical
  scales are unresolved.
- Reactive-power unit metadata, cell-voltage display precision, and output
  percentage device class remain HA-GII-3 presentation work.
- No register source migration or write-side work was included.

The cumulative-energy mappings were not moved to another register and retain
their entity keys and counter configuration. Tests prove ordinary positive
counter values are identical after the decoder correction and separately cover
high-bit unsigned behavior. Recorder continuity, reset/rollover behavior, and
old/new live interval deltas remain a hard gate for any later source or
semantic migration.

## Audit comparison

The HA-GII-1 audit baseline checked 299 mapping occurrences and 230 unique
physical mappings. Its classification counts were:

```text
MATCH                  203
SIGNEDNESS_MISMATCH     85
LENGTH_MISMATCH          3
UNIT_MISMATCH            2
NEEDS_LIVE_VALIDATION    6
```

Rerunning the audit with the corrected effective-decoder model gives:

```text
MATCH                  273
SIGNEDNESS_MISMATCH      3
LENGTH_MISMATCH          1
UNIT_MISMATCH            5
SEMANTIC_MISMATCH       11
NEEDS_LIVE_VALIDATION    6
```

The remaining length finding is I39. The three signedness occurrences are I3101
once and I3170 twice; the storage-mix legacy mappings are instead reclassified
as semantic follow-up findings. The newly visible semantic and unit findings
are not claimed fixes: the old audit classification stopped at signedness, so
correcting the decoder exposes later canonical checks for legacy/common
mappings and secondary reactive-power mappings. They remain explicit
follow-up items. No unrelated mapping disappeared from the audit.

The static list of 24 historical GII runtime findings remains retained in the
canonical audit; this consumer patch resolves only the high-confidence
two-word decoder cases and the I110/I3110 physical-length error.

## Tests and validation

The focused HA-GII-2 suite covers:

- one-word signed and unsigned values;
- two-word signed and unsigned values;
- scale/divisor handling;
- ordinary positive cumulative-energy equivalence;
- high-bit unsigned values;
- exact I3110 one-word length and independent I3111 mapping;
- unchanged warning field key and unique-ID construction;
- preservation of I3170 as a separate mapping.

The focused suite, including existing HA-5, native-block, and HA-8B
regressions, passed with 33 tests. No read-only live validation was used;
static canonical evidence and consumer tests were sufficient for this bounded
correction.

Remaining risk is limited to the explicitly deferred source-layout,
signedness, semantic, scale, and statistics-continuity cases. The branch must
be reviewed before any runtime deployment or merge.
