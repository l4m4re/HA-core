# Original ZABA22 rehosting

This report is generated from `evidence.json`; it does not replace the original binary or Ghidra artifacts.

## What I found

Unicorn executes original ZABA22 ARM/Thumb bytes in a bounded offline harness. QEMU and Renode with actual GDB sessions execute the hash-checked image to `PC=0x080020bc`. The evidence-bounded Unicorn RCC/FLASH/VTOR contract advances original reset execution to `PC=0x080021d0`, where it stops at an explicit unresolved PLLRDY poll. The separate clock state model covers HSI/HSE/PLL/SWS transitions without inventing PLL or SWS readiness. The original CRC16 function at `0x080130bc` reproduces three Modbus vectors, and the original byte-sum function at `0x080130ea` matches an independent oracle.

## Why it matters

This is original-firmware execution, not reconstructed C/Python execution. Full boot is not claimed: the required STM32F1 peripheral behavior is not sufficiently evidenced. The system-emulator path is deliberately limited to CPU/memory/debugger reachability at the RCC boundary; the clock state model remains a separately tested contract until its register semantics are sufficiently evidenced.

## Do this first

Run the Renode/GDB or QEMU/GDB runner, then use the clock-state tests and trace-driven RCC/FLASH/VTOR model as separate evidence layers. Integrate additional RCC behavior only when each register transition is supported by authoritative evidence.

## What I did not check

- Full ZABA22 boot and scheduler execution.
- Hardware-faithful RCC, GPIO, USART, CAN, SPI, flash-controller or interrupt semantics.
- Live hardware, flashing, serial access, network access or production writes.
- Post-`0x080021d0` GDB state, full boot, and hardware-faithful STM32 peripheral behavior.

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
| Renode + GDB | Yes | Original image reaches `0x080020bc`; RCC behavior is an explicit boundary |
| Clock state model | Yes, offline | HSI/HSE/PLL/SWS transitions tested; unresolved PLL/SWS remain typed blockers |

## Phase 2 peripheral and Modbus boundary

Experimentally confirmed: QEMU/GDB and Renode/GDB execute the original image to the RCC read at `PC=0x080020bc`; the Unicorn contract run records that modeled read and advances to the firmware-derived PLLRDY boundary at `0x080021d0`. Firmware-derived: the startup trace references RCC offsets `0x00`, `0x04`, `0x08`, `0x2c`, FLASH control at `0x40022000`, VTOR at `0xe000ed08`, and bounded ready-bit polling through `0x08002230`. Hardware-defined candidate semantics: RCC_CIR.HSERDYC is bit 19. The exact STM32 derivative, reset values, PLL lock and SWS settling remain unresolved.

The original Modbus path is statically bounded as `0x08024f34` ingress/CRC validation → `0x0801e46c` dispatcher → FC06/FC10 write path through `0x0802a638`. This increment does not claim UART, scheduler, persistence, transport identity, or complete register semantics, and it does not substitute the reconstructed Modbus implementation for original instructions.

## Next phase

Resolve the exact derivative and PLLRDY/SWS contract with additional authoritative evidence or an explicitly labeled emulator policy, then wire the reviewed state model into the system emulator and rerun the original reset path. Do not claim application Modbus execution until that boundary is crossed with original instructions.

## Evidence index

| ID | Class | Emulator | Entry | Claim |
|---|---|---|---|---|
| E-RH-001 | static-derived | none | `vector table` | The original ZABA22 payload and reset vector are hash-identified. |
| E-RH-002 | static-derived | none | `0x080130bc` | Ghidra instruction evidence identifies an isolated CRC16 function at 0x080130bc and a byte-sum function at 0x080130ea. |
| E-RH-003 | experimental | unicorn | `0x080130bc Thumb` | Unicorn executed the original CRC16 function bytes and reproduced the independent Modbus CRC oracle. |
| E-RH-004 | experimental | unicorn | `0x080130ea Thumb` | Unicorn executed a second original function and matched the independent byte-sum oracle. |
| E-RH-005 | experimental | unicorn | `0x08003510 Thumb` | Original reset execution reaches the first unsupported RCC MMIO read at PC 0x080020bc. |
| E-RH-006 | experimental | none | `backend availability` | The offline toolchain probe finds Unicorn, QEMU, Renode and GDB executables available in the development container. |
| E-RH-007 | experimental | unicorn | `bounded fragment suite` | The original-byte harness, vectors, trace boundary and boot blocker are reproducibly tested offline. |
| E-RH-008 | experimental | qemu-system-arm+gdb-multiarch | `0x08003510 reset vector` | QEMU executed the original payload and an actual GDB remote session stopped at the known RCC instruction. |
| E-RH-009 | static-derived | none | `startup and Modbus boundaries` | Firmware analysis bounds the minimum startup peripheral surface and the original Modbus ingress/dispatch/write path. |
| E-RH-010 | experimental | unicorn+trace-driven-peripherals | `0x08003510 reset vector` | Original reset instructions execute the RCC read and progress beyond the first blocker before stopping at the firmware-derived unbounded PLLRDY poll. |
| E-RH-011 | experimental-plus-static-derived | offline-clock-state-model | `RCC_CR/RCC_CFGR/RCC_CIR` | The offline clock model records explicit HSI/HSE/PLL/SWS transitions, reset/disable effects and distinguishes synthetic readiness timing from hardware-defined status relationships; RCC_CIR.HSERDYC uses bit 19. |
| E-RH-012 | experimental | renode+Cortex-M3+gdb-multiarch | `0x08003510 reset vector` | Renode and GDB execute the unchanged original image through the firmware-derived RCC instruction boundary; no guessed RCC behavior is used. |

## Reproduction

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q research/zaba22_original_rehosting/test_rehosting.py
PYTHONDONTWRITEBYTECODE=1 python3 -m research.zaba22_original_rehosting.backend_probe
PYTHONDONTWRITEBYTECODE=1 python3 -m research.zaba22_original_rehosting.emulator.qemu_runner
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q research/zaba22_original_rehosting/test_peripheral_execution.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q research/zaba22_original_rehosting/test_clock_state.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q research/zaba22_original_rehosting/test_system_integration.py
PYTHONDONTWRITEBYTECODE=1 python3 -m research.zaba22_original_rehosting.system_emulator.runner
```
