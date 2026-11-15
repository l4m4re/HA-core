# Original ZABA22 rehosting

This report is generated from `evidence.json`; it does not replace the original binary or Ghidra artifacts.

## What I found

Unicorn executes original ZABA22 ARM/Thumb bytes in a bounded offline harness. The original CRC16 function at `0x080130bc` reproduces three Modbus vectors, and the original byte-sum function at `0x080130ea` matches an independent oracle. Reset execution reaches the exact first unsupported RCC read at `PC=0x080020bc`, `MMIO=0x40021000`.

## Why it matters

This is original-firmware execution, not reconstructed C/Python execution. Full boot is not claimed: the required STM32F1 peripheral behavior is not sufficiently evidenced. QEMU, Renode and GDB are unavailable locally, so their absence is recorded as an environment blocker rather than hidden behind a model.

## Do this first

Install or provide pinned, reviewed QEMU/Renode/GDB runtimes in an isolated environment, then rerun the same original-byte fragment and compare trace, return value, MMIO and stop reason against the Unicorn evidence.

## What I did not check

- Full ZABA22 boot and scheduler execution.
- Hardware-faithful RCC, GPIO, USART, CAN, SPI, flash-controller or interrupt semantics.
- Live hardware, flashing, serial access, network access or production writes.
- Actual GDB remote debugging; only a prepared command file is included.

## Memory and execution contract

| Region | Address | Semantics |
|---|---:|---|
| Original flash | `0x08000000..0x0803ffff` | Hash-verified payload bytes |
| RAM | `0x20000000..0x2000ffff` | Stack, inputs, return stub and explicitly seeded CRC tables |
| MMIO boundary | `0x40000000..0x400fffff` | Explicit trap/log boundary; no invented peripheral behavior |

## Emulator comparison

| Backend | Original fragment executed here | Result |
|---|---:|---|
| Unicorn | Yes | CRC16 and byte-sum pass; reset reaches exact MMIO blocker |
| QEMU | No | `qemu-system-arm` and `qemu-arm` absent |
| Renode | No | `renode` and `dotnet` absent |

## Evidence index

| ID | Class | Emulator | Entry | Claim |
|---|---|---|---|---|
| E-RH-001 | static-derived | none | `vector table` | The original ZABA22 payload and reset vector are hash-identified. |
| E-RH-002 | static-derived | none | `0x080130bc` | Ghidra instruction evidence identifies an isolated CRC16 function at 0x080130bc and a byte-sum function at 0x080130ea. |
| E-RH-003 | experimental | unicorn | `0x080130bc Thumb` | Unicorn executed the original CRC16 function bytes and reproduced the independent Modbus CRC oracle. |
| E-RH-004 | experimental | unicorn | `0x080130ea Thumb` | Unicorn executed a second original function and matched the independent byte-sum oracle. |
| E-RH-005 | experimental | unicorn | `0x08003510 Thumb` | Original reset execution reaches the first unsupported RCC MMIO read at PC 0x080020bc. |
| E-RH-006 | experimental | none | `backend availability` | Only Unicorn is executable in the current environment; QEMU, Renode and GDB comparison cannot run locally. |
| E-RH-007 | experimental | unicorn | `bounded fragment suite` | The original-byte harness, vectors, trace boundary and boot blocker are reproducibly tested offline. |

## Reproduction

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q research/zaba22_original_rehosting/test_rehosting.py
PYTHONDONTWRITEBYTECODE=1 python3 -m research.zaba22_original_rehosting.backend_probe
```
