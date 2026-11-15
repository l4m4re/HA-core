# Original ZABA22 rehosting

This report is generated from `evidence.json`; it does not replace the original binary or Ghidra artifacts.

## What I found

Unicorn executes original ZABA22 ARM/Thumb bytes in a bounded offline harness. QEMU with an actual GDB remote session also executes the hash-checked image and reaches `PC=0x080020bc`. The original CRC16 function at `0x080130bc` reproduces three Modbus vectors, and the original byte-sum function at `0x080130ea` matches an independent oracle. Reset execution reaches the exact first unsupported RCC read at `MMIO=0x40021000`.

## Why it matters

This is original-firmware execution, not reconstructed C/Python execution. Full boot is not claimed: the required STM32F1 peripheral behavior is not sufficiently evidenced. QEMU, Renode and GDB are installed and available for follow-up comparison; backend availability is not being confused with successful original-fragment execution.

## Do this first

Use the QEMU/GDB runner for a reproducible system-emulator/debugger check, then extend the minimal trace-driven RCC/FLASH/VTOR model only when each register behavior is supported by firmware evidence. Renode remains available but unexecuted in this increment.

## What I did not check

- Full ZABA22 boot and scheduler execution.
- Hardware-faithful RCC, GPIO, USART, CAN, SPI, flash-controller or interrupt semantics.
- Live hardware, flashing, serial access, network access or production writes.
- Renode execution, full boot, and hardware-faithful STM32 peripheral behavior.

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
| QEMU + GDB | Yes | Original image reaches `0x080020bc`; GDB observes `ldr r0, [r0, #0]` |
| Renode | Available; not executed | portable `renode` 1.17.0 present with embedded .NET runtime |

## Phase 2 peripheral and Modbus boundary

Experimentally confirmed: the original reset path reaches a 32-bit read at `PC=0x080020bc`, `RCC=0x40021000`; QEMU/GDB and Unicorn agree on that boundary. Firmware-derived: the startup trace references RCC offsets `0x00`, `0x04`, `0x08`, `0x2c`, FLASH control at `0x40022000`, VTOR at `0xe000ed08`, and bounded ready-bit polling through `0x08002230`. The exact STM32 derivative and reset values remain unresolved, so no arbitrary register model is installed.

The original Modbus path is statically bounded as `0x08024f34` ingress/CRC validation → `0x0801e46c` dispatcher → FC06/FC10 write path through `0x0802a638`. This increment does not claim UART, scheduler, persistence, transport identity, or complete register semantics, and it does not substitute the reconstructed Modbus implementation for original instructions.

## Next phase

Add only a trace-driven RCC/FLASH/VTOR model whose read/write values are justified by observed firmware tests, then rerun the original reset path. Keep Renode as a separate comparison experiment after a reviewed STM32 platform contract exists.

## Evidence index

| ID | Class | Emulator | Entry | Claim |
|---|---|---|---|---|
| E-RH-001 | static-derived | none | `vector table` | The original ZABA22 payload and reset vector are hash-identified. |
| E-RH-002 | static-derived | none | `0x080130bc` | Ghidra instruction evidence identifies an isolated CRC16 function at 0x080130bc and a byte-sum function at 0x080130ea. |
| E-RH-003 | experimental | unicorn | `0x080130bc Thumb` | Unicorn executed the original CRC16 function bytes and reproduced the independent Modbus CRC oracle. |
| E-RH-004 | experimental | unicorn | `0x080130ea Thumb` | Unicorn executed a second original function and matched the independent byte-sum oracle. |
| E-RH-005 | experimental | unicorn | `0x08003510 Thumb` | Original reset execution reaches the first unsupported RCC MMIO read at PC 0x080020bc. |
| E-RH-006 | experimental | none | `backend availability` | Unicorn and QEMU/GDB have executed original ZABA22 fragments; Renode is available but only its tool availability has been verified. |
| E-RH-007 | experimental | unicorn | `bounded fragment suite` | The original-byte harness, vectors, trace boundary and boot blocker are reproducibly tested offline. |
| E-RH-008 | experimental | qemu-system-arm+gdb-multiarch | `0x08003510 reset vector` | QEMU executed the original payload and an actual GDB remote session stopped at the known RCC instruction. |
| E-RH-009 | static-derived | none | `startup and Modbus boundaries` | Firmware analysis bounds the minimum startup peripheral surface and the original Modbus ingress/dispatch/write path. |

## Reproduction

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q research/zaba22_original_rehosting/test_rehosting.py
PYTHONDONTWRITEBYTECODE=1 python3 -m research.zaba22_original_rehosting.backend_probe
PYTHONDONTWRITEBYTECODE=1 python3 -m research.zaba22_original_rehosting.emulator.qemu_runner
```
