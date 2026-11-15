"""Run the unchanged ZABA22 payload under Renode and GDB.

The platform deliberately maps only CPU, flash, RAM, NVIC and SCB space. It
does not model RCC or any application peripheral. A breakpoint at the known
RCC instruction therefore proves original CPU/memory/debugger reachability;
it must not be interpreted as a successful boot.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from shutil import which
import subprocess
import time

from ..harness import EXPECTED_PAYLOAD_SHA256, load_payload, payload_path

RCC_READ_PC = 0x080020BC
RENODE_GDB_PORT = 3334
REPO_ROOT = Path(__file__).resolve().parents[3]
RENODE_SCRIPT = Path(__file__).with_name("renode-zaba22.resc")


@dataclass(frozen=True)
class RenodeGdbResult:
    """Evidence from one Renode/GDB original-image run."""

    payload_sha256: str
    renode_command: tuple[str, ...]
    gdb_command: tuple[str, ...]
    transcript: str
    breakpoint_hit: bool
    renode_exit_code: int
    gdb_exit_code: int


def run_renode_gdb(*, timeout: float = 20.0) -> RenodeGdbResult:
    """Load original bytes and stop GDB at the first known RCC instruction."""

    renode = which("renode")
    gdb = which("gdb-multiarch")
    if renode is None or gdb is None:
        missing = [
            name
            for name, path in (("renode", renode), ("gdb-multiarch", gdb))
            if path is None
        ]
        raise RuntimeError(f"missing required executable(s): {', '.join(missing)}")

    image = payload_path()
    load_payload(image)
    renode_command = (
        renode,
        "--plain",
        "--disable-gui",
        "--hide-monitor",
        str(RENODE_SCRIPT),
    )
    process = subprocess.Popen(
        renode_command,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_gdb(process, timeout=timeout)
        gdb_commands = (
            "set architecture arm",
            "set endian little",
            "set pagination off",
            f"target remote 127.0.0.1:{RENODE_GDB_PORT}",
            "x/2wx 0x08000000",
            "info registers pc sp",
            f"break *{RCC_READ_PC:#x}",
            "continue",
            "info registers pc",
            "x/2i $pc",
            "detach",
            "quit",
        )
        gdb_command = (
            gdb,
            "-q",
            "-batch",
            *(argument for command in gdb_commands for argument in ("-ex", command)),
        )
        gdb_process = subprocess.run(
            list(gdb_command), capture_output=True, text=True, timeout=timeout, check=False
        )
        transcript = gdb_process.stdout + gdb_process.stderr
    finally:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)

    return RenodeGdbResult(
        payload_sha256=EXPECTED_PAYLOAD_SHA256,
        renode_command=renode_command,
        gdb_command=gdb_command,
        transcript=transcript,
        breakpoint_hit=f"Breakpoint 1, {RCC_READ_PC:#010x}" in transcript,
        renode_exit_code=process.returncode,
        gdb_exit_code=gdb_process.returncode,
    )


def _wait_for_gdb(process: subprocess.Popen[str], *, timeout: float) -> None:
    """Wait until Renode has opened its GDB socket, without hiding failures."""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output, _ = process.communicate()
            raise RuntimeError(f"Renode exited before GDB startup: {output}")
        # Do not probe the TCP port: Renode's GDB server accepts one client,
        # and a readiness connection would consume the debugger session.
        time.sleep(0.1)
        if time.monotonic() >= deadline - timeout + 1.0:
            return
    raise TimeoutError("Renode did not open its GDB server before timeout")


def main() -> None:
    """Print the reproducible Renode/GDB evidence transcript."""

    result = run_renode_gdb()
    print(f"payload_sha256={result.payload_sha256}")  # noqa: T201
    print(f"breakpoint_hit={result.breakpoint_hit}")  # noqa: T201
    print(result.transcript, end="")  # noqa: T201


if __name__ == "__main__":
    main()
