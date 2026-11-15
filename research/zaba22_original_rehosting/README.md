# Original ZABA22 offline rehosting

This package executes bytes from the original
`external/growatt-firmware/ALBA18/ZABA22-payload.bin`. It never connects to an
inverter, battery, production Home Assistant, serial port, or network service.

The working backend is Unicorn. It maps:

| Region | Address | Purpose |
|---|---:|---|
| Original flash | `0x08000000..0x0803ffff` | Unmodified ZABA22 payload |
| RAM | `0x20000000..0x2000ffff` | Stack, input, return stub, harness-seeded CRC tables |
| MMIO boundary | `0x40000000..0x400fffff` | Explicit trap range; no peripheral semantics are invented |

The executable original-code slice is `modbus_crc16_table_lookup` at
`0x080130bc` (Thumb). The harness seeds the two RAM lookup tables because the
standalone stock table initialization path was not recovered. The executed
instructions themselves remain original payload bytes. `0x080130ea` is also
covered as a dependency-free original byte-sum function.

The reset vector is probed from the original vector table. Boot reaches the
first unsupported RCC access at `PC=0x080020bc`, `address=0x40021000`; that is
recorded as a blocker, not bypassed with a guessed peripheral model.

QEMU, Renode and GDB are installed in the development container and are
probed by `backend_probe.py`. The Renode installation is the portable release
with its embedded .NET runtime; a separate `dotnet` command is not required.
The prepared GDB commands are in `gdb-zaba22.txt`. Availability does not claim
that the original fragment has already been executed through every backend.

Run from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q research/zaba22_original_rehosting/test_rehosting.py
PYTHONDONTWRITEBYTECODE=1 python3 -m research.zaba22_original_rehosting.backend_probe
```
