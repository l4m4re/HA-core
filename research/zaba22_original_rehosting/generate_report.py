from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parent
EVIDENCE = json.loads((ROOT / "evidence.json").read_text())


def main() -> None:
    print("# Original ZABA22 rehosting")
    print()
    print("This report is generated from `evidence.json`; it does not replace the original binary or Ghidra artifacts.")
    print()
    print("## What I found")
    print()
    print("Unicorn executes original ZABA22 ARM/Thumb bytes in a bounded offline harness. The original CRC16 function at `0x080130bc` reproduces three Modbus vectors, and the original byte-sum function at `0x080130ea` matches an independent oracle. Reset execution reaches the exact first unsupported RCC read at `PC=0x080020bc`, `MMIO=0x40021000`.")
    print()
    print("## Why it matters")
    print()
    print("This is original-firmware execution, not reconstructed C/Python execution. Full boot is not claimed: the required STM32F1 peripheral behavior is not sufficiently evidenced. QEMU, Renode and GDB are unavailable locally, so their absence is recorded as an environment blocker rather than hidden behind a model.")
    print()
    print("## Do this first")
    print()
    print("Install or provide pinned, reviewed QEMU/Renode/GDB runtimes in an isolated environment, then rerun the same original-byte fragment and compare trace, return value, MMIO and stop reason against the Unicorn evidence.")
    print()
    print("## What I did not check")
    print()
    print("- Full ZABA22 boot and scheduler execution.")
    print("- Hardware-faithful RCC, GPIO, USART, CAN, SPI, flash-controller or interrupt semantics.")
    print("- Live hardware, flashing, serial access, network access or production writes.")
    print("- Actual GDB remote debugging; only a prepared command file is included.")
    print()
    print("## Memory and execution contract")
    print()
    print("| Region | Address | Semantics |")
    print("|---|---:|---|")
    print("| Original flash | `0x08000000..0x0803ffff` | Hash-verified payload bytes |")
    print("| RAM | `0x20000000..0x2000ffff` | Stack, inputs, return stub and explicitly seeded CRC tables |")
    print("| MMIO boundary | `0x40000000..0x400fffff` | Explicit trap/log boundary; no invented peripheral behavior |")
    print()
    print("## Emulator comparison")
    print()
    print("| Backend | Original fragment executed here | Result |")
    print("|---|---:|---|")
    print("| Unicorn | Yes | CRC16 and byte-sum pass; reset reaches exact MMIO blocker |")
    print("| QEMU | No | `qemu-system-arm` and `qemu-arm` absent |")
    print("| Renode | No | `renode` and `dotnet` absent |")
    print()
    print("## Evidence index")
    print()
    print("| ID | Class | Emulator | Entry | Claim |")
    print("|---|---|---|---|---|")
    for item in EVIDENCE:
        print(f"| {item['id']} | {item['evidence_class']} | {item['emulator']} | `{item['entry']}` | {item['claim']} |")
    print()
    print("## Reproduction")
    print()
    print("```sh")
    print("PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q research/zaba22_original_rehosting/test_rehosting.py")
    print("PYTHONDONTWRITEBYTECODE=1 python3 -m research.zaba22_original_rehosting.backend_probe")
    print("```")


if __name__ == "__main__":
    main()
