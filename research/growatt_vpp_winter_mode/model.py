"""Evidence-preserving offline model for the Winter Mode/VPP interaction.

This model deliberately does not claim to emulate a live inverter.  It keeps
the recovered ZABA22 transition separate from the observed ZABA23 boundary and
represents readback and downstream application as independent evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


EvidenceClass = Literal["experimental", "firmware-derived", "hypothesis"]
FirmwareProfile = Literal["zaba22", "zaba23-observed"]
Route = Literal["legacy", "vpp-tou", "vpp-remote-timer", "unresolved"]


@dataclass(frozen=True)
class Observation:
    """One recorded fact or explicitly bounded inference."""

    evidence_id: str
    register: str
    operation: str
    value: object
    evidence_class: EvidenceClass
    source: str
    claim: str
    confidence: Literal["high", "medium", "low"]


@dataclass(frozen=True)
class WriteOutcome:
    """Front-end result of an offline write replay."""

    register: str
    value: int
    accepted: bool
    exception_code: int | None = None


@dataclass
class WinterVppState:
    """Small replay model for the five requested registers.

    ``zaba23-observed`` is a fixture for the specific observed boundary, not a
    universal firmware rule.  H192 is stored but has no derived meaning.
    """

    firmware_profile: FirmwareProfile = "zaba22"
    h30100: int = 0
    h30407: int = 0
    h3037: int = 0
    h30475: int = 0
    h192: int = 0
    pending_mask: int = 0
    bridge_latch: bool = False
    public_readback: dict[str, int] = field(default_factory=dict)
    write_log: list[WriteOutcome] = field(default_factory=list)

    def write(self, register: str, value: int) -> WriteOutcome:
        """Replay an FC06/FC10 word without touching external hardware."""

        if not isinstance(value, int) or not 0 <= value <= 0xFFFF:
            raise ValueError("register values must be unsigned 16-bit words")

        accepted = True
        exception_code: int | None = None
        if register == "H30100":
            accepted = value in (0, 1)
            if accepted:
                self.h30100 = value
        elif register == "H30407":
            accepted = value in (0, 1)
            if accepted:
                self.h30407 = value
        elif register == "H3037":
            accepted = 10 <= value <= 100
            if accepted:
                self.h3037 = value
        elif register == "H30475":
            accepted = 10 <= value <= 35
            if self.firmware_profile == "zaba23-observed" and value == 20:
                accepted = False
            if accepted:
                self.h30475 = value
        elif register == "H192":
            self.h192 = value
        else:
            raise ValueError(f"unsupported register: {register}")

        if not accepted:
            exception_code = 1
        outcome = WriteOutcome(register, value, accepted, exception_code)
        self.write_log.append(outcome)
        return outcome

    def worker_step(self) -> Route:
        """Run one recovered worker decision and return only the route."""

        if self.h30100 != 1:
            return "legacy"
        if self.pending_mask:
            return "unresolved"
        if self.firmware_profile == "zaba22" and not self.bridge_latch:
            self.h30475 = min(self.h3037, 35)
            self.bridge_latch = True
        return "vpp-remote-timer" if self.h30407 == 1 else "vpp-tou"

    def read(self, register: str) -> int | None:
        """Return public readback, allowing a captured shadow to be replayed."""

        if register in self.public_readback:
            return self.public_readback[register]
        return {
            "H30100": self.h30100,
            "H30407": self.h30407,
            "H3037": self.h3037,
            "H30475": self.h30475,
            "H192": self.h192,
        }.get(register)


def classify_transition(observation: Observation) -> str:
    """Return the evidence class without upgrading its confidence."""

    return observation.evidence_class
