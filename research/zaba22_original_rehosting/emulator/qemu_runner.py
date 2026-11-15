"""Run the original ZABA22 image in QEMU with a real GDB remote session."""

from dataclasses import dataclass
from pathlib import Path
from shutil import which
import subprocess

from research.zaba22_original_rehosting.harness import (
    EXPECTED_PAYLOAD_SHA256,
    load_payload,
    payload_path,
)

QEMU_MACHINE = "stm32vldiscovery"
FLASH_BASE = 0x08000000
RCC_READ_PC = 0x080020BC


@dataclass(frozen=True)
class QemuGdbResult:
    """Evidence captured from one original-image QEMU/GDB run."""

    payload_sha256: str
    qemu_command: tuple[str, ...]
    gdb_command: tuple[str, ...]
    transcript: str
    breakpoint_hit: bool
    exit_code: int


def run_qemu_gdb(
    image: Path | None = None,
    *,
    port: int = 12345,
    timeout: float = 20.0,
) -> QemuGdbResult:
    """Boot the original bytes and stop at the first known RCC instruction."""

    qemu = which("qemu-system-arm")
    gdb = which("gdb-multiarch")
    if qemu is None or gdb is None:
        missing = [name for name, path in (("qemu-system-arm", qemu), ("gdb-multiarch", gdb)) if path is None]
        raise RuntimeError(f"missing required executable(s): {', '.join(missing)}")

    image = image or payload_path()
    load_payload(image)
    qemu_command = (
        qemu,
        "-M",
        QEMU_MACHINE,
        "-display",
        "none",
        "-monitor",
        "none",
        "-serial",
        "none",
        "-no-reboot",
        "-S",
        "-gdb",
        f"tcp:127.0.0.1:{port}",
        "-device",
        f"loader,file={image},addr={FLASH_BASE:#x}",
        "-device",
        "loader,addr=0xE000ED08,data=0x08000000,data-len=4",
        "-device",
        "loader,addr=0xE000ED0C,data=0x00000000,data-len=4",
    )
    gdb_commands = (
        "set architecture arm",
        "set endian little",
        "set pagination off",
        f"target remote 127.0.0.1:{port}",
        "x/2wx 0x08000000",
        "info registers pc sp",
        f"break *{RCC_READ_PC:#x}",
        "continue",
        "info registers pc",
        "x/2i $pc",
        "detach",
        "quit",
    )
    process = subprocess.Popen(
        qemu_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        gdb_process = subprocess.run(
            [gdb, "-q", "-batch", *(argument for command in gdb_commands for argument in ("-ex", command))],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        transcript = gdb_process.stdout + gdb_process.stderr
    finally:
        process.kill()
        process.communicate(timeout=5)

    return QemuGdbResult(
        payload_sha256=EXPECTED_PAYLOAD_SHA256,
        qemu_command=qemu_command,
        gdb_command=(gdb, "-q", "-batch", *gdb_commands),
        transcript=transcript,
        breakpoint_hit=f"Breakpoint 1, {RCC_READ_PC:#010x}" in transcript,
        exit_code=gdb_process.returncode,
    )


def main() -> None:
    """Print one reproducible QEMU/GDB evidence transcript."""

    result = run_qemu_gdb()
    print(f"payload_sha256={result.payload_sha256}")  # noqa: T201
    print(f"breakpoint_hit={result.breakpoint_hit}")  # noqa: T201
    print(result.transcript, end="")  # noqa: T201


if __name__ == "__main__":
    main()
