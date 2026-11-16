# ZABA22 Phase 5 — VPP behavioral investigation

Status: evidence package complete for the bounded paths below. The available
original image is ZABA22; the live inverter observations are ZABA23 and are
never treated as the same firmware.

## Reproduction

```text
python3 -m pytest -q research/zaba22_original_rehosting/test_vpp_original.py
```

The test executes original ARM/Thumb bytes from the SHA-256-pinned payload.
It records the original response bytes, stop PC and SRAM writes. The fixtures
are offline and hypothetical unless a source is explicitly labelled capture-
derived.

## State and behavior matrix

| Path / state | Result | Evidence class |
|---|---|---|
| ZABA22 FC06, `pending_mask=0` | The original pre-gate passes the mask check, then reaches an unmodelled downstream dispatch and stops on an unmapped read. No exception is fabricated. | Original execution, negative boundary |
| ZABA22 FC06, `pending_mask=1` or `0x2000` | Original response buffer contains `00 86 01`; execution stops at `0x0801E9BC` before downstream dispatch. | Original execution |
| ZABA22 bridge, `H30100=0`, latch clear | No H30475 write. | Original execution |
| ZABA22 bridge, `H30100=1`, latch clear, H3037=10/35 | H30475 is written to 10/35, latch bit 0 is set, and dirty state is written. | Original execution |
| ZABA22 bridge, `H30100=1`, latch clear, H3037=36/100 | Original code first stores the source byte and then clamps H30475 to 35. | Original execution |
| ZABA22 bridge, latch set | No bridge write. | Original execution |
| ZABA22 direct H30405/H30406 | Validator accepts raw values 10..35; stores are at `0x2000AE06/08` and set dirty bit `0x08000000`. | Firmware-derived static evidence |
| ZABA22 direct H30475 | Validator accepts raw values 10..35; store is at `0x2000AE92` and sets dirty bit `0x08000000`. | Firmware-derived static evidence |
| ZABA22 direct H30475=20 | Value is in the recovered 10..35 range. A rejection therefore requires an earlier gate, another version, or a different request path; the common `0x86/0x01` response is not by itself diagnostic. | Static conclusion; live mismatch unresolved |
| Live ZABA23 H30475=20 with H30100=0 or 1 | Exception `0x86/0x01`, H30475 remained 0. | Capture-derived ZABA23 observation |
| Live ZABA23 Winter sequence | H30100=1, H30405=29, H30406=29, H30475=13 was acknowledged/echoed; a later 30/30/10 sequence was also acknowledged. Later provider scans returned zeros. | Capture-derived ZABA23 observation |

## State transitions

The recovered ZABA22 worker gates the refresh group on
`0x2000EB64 == 0`. If non-zero, the group containing the H3037→H30475
bridge is skipped. The separate byte latch at `0x2000E6EB`, bit 0, is checked
inside the bridge and is set after the first successful bridge. Thus the
minimal ZABA22 transition is:

```text
pending != 0                         -> no refresh group
pending == 0, latch bit 0 == 1       -> bridge skipped
pending == 0, latch bit 0 == 0,
  H30100 != 1                        -> bridge skipped
pending == 0, latch bit 0 == 0,
  H30100 == 1                        -> H30475 := min(H3037, 35), latch := 1
```

The first and last transitions above were executed as original code at their
respective bounded entrypoints. The worker's call sequencing and its full
peripheral environment were not emulated.

## Readback and portal correlation

An acknowledged write is not proof that a later provider scan read the same
physical state. The broker invalidates overlapping cache blocks before writes,
but the historical scan artifacts do not contain a joinable cache generation,
snapshot ID or source transaction for every zero. Therefore the zero
readbacks remain a provider/cache-versus-physical ambiguity, not proof of an
inverter overwrite. Portal success likewise has no request identity that can
be joined to a specific Modbus transaction. See the PiITM cache evidence and
the capture audit in the existing winter-mode evidence package.

## ARK/BDC analysis

The inspected ZABA22 dataflow does not prove an ARK/BDC-derived value reaches
H30100, `pending_mask`, the bridge latch, or the H30475 validator. BDC/SYS-COM
and candidate ARK/ECAN paths remain separate unresolved protocol paths. A
transmitted command would not by itself prove an electrically applied effect.

## What ZABA22 explains, and what it does not

ZABA22 explains the existence of a one-shot H3037→H30475 bridge, its 35 clamp,
the direct 10..35 validator, the dirty bit, and a pending-mask route that can
produce `0x86/0x01` before value validation. It does not explain the observed
ZABA23 rejection of H30475=20 if that request reached the equivalent validator,
nor does it establish that ZABA23 retains the ZABA22 bridge. The acknowledged
Winter values followed by zero provider reads remain version/cache/readpath
hypotheses.

## Ranked missing evidence

1. A hash-identified ZABA23 code image or an instruction trace of its FC06
   validator and VPP worker.
2. Synchronized write and immediate physical FC03/FC04 reads carrying broker
   source-transaction IDs, cache generation and snapshot IDs.
3. A synchronized capture of `H30100`, H3037, H30475, H30407, H192,
   `pending_mask` and the latch across one worker interval.
4. A direct ZABA23 diagnostic or RAM trace showing which producer sets the
   pending bit and whether it is cleared by the recovery worker.
5. ARK/BDC frame-to-SRAM dataflow evidence, only if the first four items leave
   the rejection unexplained.

## Sources and limitations

- Original payload and Ghidra/ARM analysis under `external/growatt-firmware`.
- Existing live captures and broker cache contract under
  `external/growatt-rtu-broker` and `research/growatt_vpp_winter_mode`.
- Historical portal context: [GitHub issue #494](https://github.com/0xAHA/Growatt_ModbusTCP/issues/494).
- No live inverter, battery, serial bus, production Home Assistant, reset,
  firmware update, support interaction or DSP emulation was used.
