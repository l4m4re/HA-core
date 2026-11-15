# ZABA22 system-emulator path

This package provides a reproducible real-CPU, memory, and debugger path for
the unchanged `external/growatt-firmware/ALBA18/ZABA22-payload.bin`.

## Reproduction

From the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m research.zaba22_original_rehosting.system_emulator.runner
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q research/zaba22_original_rehosting/test_system_integration.py
```

The runner starts Renode 1.17.0 with the local `renode-zaba22.repl` map,
loads the payload at `0x08000000`, connects `gdb-multiarch` to Renode's GDB
server, and continues to the firmware-derived RCC instruction at
`0x080020bc`. The same focused test also runs the existing QEMU/GDB path.

## Capability boundary

The Renode map contains Cortex-M3 CPU state, original flash, RAM, the NVIC/SCB
region, and a reset-vector alias at `0x00000000` required by Renode's reset
loader. The alias contains the same unchanged image bytes; it is loader state,
not modified firmware. RCC, USART, GPIO, CAN, SPI, flash-controller and
interrupt behavior beyond the NVIC are intentionally absent.

Therefore the exact demonstrated result is debugger-observed execution of
original instructions through `0x080020bc` on both QEMU and Renode. Full boot
and application Modbus execution remain blocked by the unresolved STM32F1 RCC
contract (the next read is at `0x40021000`). A zero-filled or guessed RCC model
would fabricate control flow and is not used.

