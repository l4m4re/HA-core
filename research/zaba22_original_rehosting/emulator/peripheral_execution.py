"""Run original reset code with only the evidence-bounded peripheral contract."""

from dataclasses import dataclass
from typing import Any

from unicorn import (
    UC_ARCH_ARM,
    UC_HOOK_CODE,
    UC_HOOK_MEM_READ,
    UC_HOOK_MEM_WRITE,
    UC_MODE_THUMB,
    UC_MEM_WRITE,
    Uc,
    UcError,
)
from unicorn.arm_const import UC_ARM_REG_R13

from research.zaba22_original_rehosting.harness import (
    FLASH_BASE,
    FLASH_SIZE,
    RAM_BASE,
    RAM_SIZE,
    RETURN_STUB,
    STACK_TOP,
    load_payload,
)
from research.zaba22_original_rehosting.peripherals import TraceDrivenPeripherals
from research.zaba22_original_rehosting.peripherals.model import (
    RCC_CR,
    PLL_READY,
    PeripheralBlocker,
    UnboundedPollBlocker,
)

MMIO_BASE = 0x40000000
MMIO_SIZE = 0x100000
SCB_BASE = 0xE000E000
SCB_SIZE = 0x1000


@dataclass(frozen=True)
class PeripheralExecutionResult:
    """Evidence from bounded original reset execution with the contract model."""

    stop_reason: str
    trace: tuple[tuple[int, int], ...]
    peripheral_events: tuple[dict[str, int | str], ...]
    blocker: str | None
    payload_sha256: str


def execute_reset_with_peripherals(
    *, hse_ready_after_polls: int | None = 3, max_instructions: int = 20_000
) -> PeripheralExecutionResult:
    """Execute original reset instructions while trapping unsupported MMIO."""

    payload = load_payload()
    model = TraceDrivenPeripherals(hse_ready_after_polls=hse_ready_after_polls)
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    uc.mem_map(FLASH_BASE, FLASH_SIZE)
    uc.mem_write(FLASH_BASE, payload)
    uc.mem_map(RAM_BASE, RAM_SIZE)
    uc.mem_map(MMIO_BASE, MMIO_SIZE)
    uc.mem_map(SCB_BASE, SCB_SIZE)

    trace: list[tuple[int, int]] = []
    events: list[dict[str, int | str]] = []
    blocker: str | None = None

    def code_hook(_uc: Uc, address: int, size: int, _user_data: Any) -> None:
        trace.append((address & ~1, size))

    def memory_hook(
        _uc: Uc, access: int, address: int, size: int, value: int, _user_data: Any
    ) -> None:
        nonlocal blocker
        if not (MMIO_BASE <= address < MMIO_BASE + MMIO_SIZE or SCB_BASE <= address < SCB_BASE + SCB_SIZE):
            return
        direction = "write" if access == UC_MEM_WRITE else "read"
        try:
            if direction == "read":
                if address == RCC_CR:
                    model.advance_time()
                    if 0x080021D0 <= trace[-1][0] <= 0x080021E0 and not model.poll_state.pll_ready:
                        raise UnboundedPollBlocker("RCC_CR.PLLRDY", PLL_READY, trace[-1][0])
                result = model.read(address, width=size, pc=trace[-1][0])
                _uc.mem_write(address, result.to_bytes(size, "little"))
                event_value = result
            else:
                model.write(address, value, width=size, pc=trace[-1][0])
                event_value = value
        except PeripheralBlocker as exc:
            blocker = str(exc)
            _uc.emu_stop()
            return
        events.append({"operation": direction, "address": address, "width": size, "value": event_value, "pc": trace[-1][0]})

    uc.hook_add(UC_HOOK_CODE, code_hook)
    uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, memory_hook)
    initial_sp = int.from_bytes(payload[0:4], "little")
    reset = int.from_bytes(payload[4:8], "little") & ~1
    uc.reg_write(UC_ARM_REG_R13, initial_sp)
    error: str | None = None
    try:
        uc.emu_start(reset | 1, 0, count=max_instructions)
    except UcError as exc:
        error = str(exc)

    if error:
        stop_reason = "emulator_error"
        blocker = error
    elif blocker:
        stop_reason = "peripheral_blocker"
    else:
        stop_reason = "instruction_limit"
    return PeripheralExecutionResult(stop_reason, tuple(trace), tuple(events), blocker, model_hash(payload))


def model_hash(payload: bytes) -> str:
    """Return the payload digest without making it part of emulator state."""

    import hashlib

    return hashlib.sha256(payload).hexdigest()
