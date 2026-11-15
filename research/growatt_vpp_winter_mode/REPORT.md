# Growatt MIN TL-XH Winter Mode / VPP interaction

This report is generated from `evidence.json` by `generate_report.py`.
It is an offline reconstruction; no inverter, battery, or production Home Assistant was contacted.

## What I found

The evidence supports a ZABA22 route selector but not a universal MIN TL-XH rule. H30100 selects legacy versus VPP in the recovered firmware; H30407 selects VPP remote-timer versus VPP-TOU. The ZABA22 bridge can copy H3037 to H30475 once, clamped to 35, when its pending mask and latch gates permit it. A live ZABA23 experiment did not show that bridge and rejected H30475=20. H192=64 is a confirmed physical write with unresolved bit-6 semantics.

## Why it matters

A successful portal response or Modbus echo cannot be treated as proof of persistence, public readback, or downstream battery application. The ZABA22 reconstruction and ZABA23 observation are both valid within their scopes and must remain separate until a version-matched experiment closes the gap.

## Do this first

1. Capture a version-matched sequence with direct physical post-write reads for H30100, H30407, H3037, H30475, and H192, plus a portal request identifier that can be joined to the Modbus trace.

## What I did not check

- No live device interaction was performed.
- No evidence closes the ARK/ALBA/C2000 downstream consumer for these values.
- No H30407 write/transition was present in the inspected captures.

## State model

```text
H30100 != 1
  -> legacy route

H30100 == 1
  -> VPP worker
  -> H30407 == 1: remote-timer route
  -> H30407 != 1: VPP-TOU route

ZABA22 only, pending_mask == 0, bridge_latch == 0:
  H30475 := min(H3037, 35)
  bridge_latch := 1

H192 = 64
  -> physical write confirmed
  -> bit 6 meaning unresolved
```

## Transition classification

| Transition | Classification | Evidence boundary |
|---|---|---|
| H30100=0 → 1 selects VPP | Firmware-derived; live write acknowledged | Does not prove downstream application |
| H30100=1, H30407=1 selects remote timer | Firmware-derived only | No live H30407 write found |
| H30100=1, H30407!=1 selects VPP-TOU | Firmware-derived only | No live H30407 transition found |
| H3037 → H30475 | ZABA22-derived, contradicted as universal by ZABA23 | 300 s ZABA23 observation showed no copy |
| H30475 direct write | Value/state/firmware dependent | 10 acknowledged; 20 rejected on ZABA23 |
| H192=64 | Experimentally confirmed write | Meaning of bit 6 unresolved |

## Portal and Modbus correlation

The inspected Winter Mode sequence contains CRC-valid, physically acknowledged writes H30100=1, H30405=30, H30406=30, H30475=10, and H192=64. A separate sequence used 29/29/13. Later scans reported H30100=1 but H30405/H30406/H30475=0, so the result is a readback/provider discrepancy rather than proof of persistence. A portal success with no joined request/response remains unresolved. A separate TOU period-9 operation wrote raw address 3054 with FC16 and exposed readback at H3058-H3059, indicating an address/alias/dispatch issue.

## Contradictions and unresolved hypotheses

- ZABA22 static behavior predicts H3037→H30475 synchronization; ZABA23 did not exhibit it.
- ZABA22 validation accepts H30475=20 in its recovered path; ZABA23 rejected it with exception 0x01.
- Physical acknowledgements coexist with zero public readback for Winter Mode values.
- H192 is namespace-ambiguous across holding/input/protocol documentation; bit 6 has no established meaning.
- The downstream ARK/ALBA/C2000 consumer and any capability gate are unresolved.

## Evidence index

| ID | Class | Register | Claim | Source |
|---|---|---|---|---|
| E-P1-001 | firmware-derived | H30100/H3037/H30475 | The recovered ZABA22 ARM path contains a one-shot H3037 to H30475 bridge. | `external/growatt-firmware/reports/ZABA22/focused/zaba22_h3037_h30475_annotated.c` |
| E-P1-002 | firmware-derived | H30100/H30407 | The recovered worker selects legacy versus VPP, then remote timer versus VPP-TOU. | `external/growatt-firmware/reports/ZABA22/focused/zaba22_h3037_h30475_annotated.c` |
| E-P1-004 | experimental | H30100/H3037/H30475 | The observed ZABA23 experiment did not show the ZABA22 bridge and rejected H30475=20. | `external/growatt-firmware/reports/live/h3037-h30475-zaba23-phase-d-authority-20261113.jsonl` |
| E-P1-005 | experimental | H192 | FC06 H192=64 was physically forwarded and echoed; bit 6 meaning is unresolved. | `external/growatt-rtu-broker/logs/growatt_shine_write_capture_20261112_171302.jsonl` |
| E-P1-007 | experimental | H30100/H30405/H30406/H30475 | A Winter Mode sequence was physically acknowledged, while later public readback was zero. | `external/growatt-rtu-broker/logs/growatt_all_write_capture_20261113_154655.jsonl` |
| E-P2-001 | experimental | H30100 | FC06 H30100=1 was physically forwarded and acknowledged, without same-transaction readback. | `external/growatt-rtu-broker/logs/growatt_all_write_capture_20261113_154655.jsonl` |
| E-P2-002 | experimental | H30405 | FC06 H30405=30 was physically forwarded and acknowledged. | `external/growatt-rtu-broker/logs/growatt_all_write_capture_20261113_154655.jsonl` |
| E-P2-003 | experimental | H30406 | FC06 H30406=30 was physically forwarded and acknowledged. | `external/growatt-rtu-broker/logs/growatt_all_write_capture_20261113_154655.jsonl` |
| E-P2-004 | experimental | H30475 | FC06 H30475=10 was physically forwarded and acknowledged, without direct post-write readback. | `external/growatt-rtu-broker/logs/growatt_all_write_capture_20261113_154655.jsonl` |
| E-P2-005 | experimental | H192 | FC06 H192=64 was physically forwarded and acknowledged; semantic meaning is unresolved. | `external/growatt-rtu-broker/logs/growatt_all_write_capture_20261113_154655.jsonl` |
| E-P2-006 | experimental | H30407 | No H30407 write was found in the inspected write captures. | `external/growatt-rtu-broker/logs/growatt_all_write_capture_20261113_154655.jsonl` |
| E-P2-008 | experimental | H30407 | The inspected scan reported H30407=0; no transition was observed. | `.staging/ha-config/growatt_register_scan_20261115_001353.csv` |
| E-P2-009 | experimental | H30475 | The scan did not expose H30475=10 after the acknowledged write; this is a provider/readback discrepancy. | `.staging/ha-config/growatt_register_scan_20261115_001353.csv` |
| E-P3-007 | firmware-derived | H30407 | With H30100=1, H30407=1 selects the remote-timer path; H30407!=1 selects VPP-TOU. | `external/growatt-firmware/open-firmware/docs/zaba22-vpp-state-machine.md` |
| E-P3-009 | experimental | H30100 | Portal success without a joined Modbus request is insufficient evidence of inverter application. | `.staging/winter-mode-tou-issue-report.md` |

## Reproduction

```sh
python3 research/growatt_vpp_winter_mode/generate_report.py > /tmp/growatt-report.md
python3 -m pytest research/growatt_vpp_winter_mode/test_model.py
```

The model is intentionally not a live Modbus client and cannot write to an inverter.
