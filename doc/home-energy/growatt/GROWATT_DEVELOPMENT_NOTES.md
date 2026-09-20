# Agent Instructions

This repository contains the **Growatt Local Home Assistant integration**. The goal is a dependable, user-configurable integration for local Growatt Modbus connections, including direct serial and network transports.

This is the Growatt workstream within the wider home-energy project in the HA-core workspace. See [`../../../ROADMAP.md`](../../../ROADMAP.md) for the cross-system plan; this workspace's [`ROADMAP.md`](ROADMAP.md) covers Growatt-specific work.

## Project plan

Read [`ROADMAP.md`](ROADMAP.md) before starting project work. It records the current state, planned user-facing setup, sensor selection, validation, and the eventual Raspberry Pi production update. Keep it current when a phase is completed or the plan changes. Treat the detailed validation and production cutover documents linked there as the source of evidence and cutover requirements.

The runtime register map and entity descriptions are distinct from the broader Growatt register research/specification repository. Do not assume that a documented register is safe or useful to expose in this integration without model applicability, decoding, and validation evidence.
Before adding broad register or sensor coverage, complete the reviewed register-map reconciliation in [`ROADMAP.md`](ROADMAP.md); do not bulk-generate runtime entities from the research specification.

## Implementation boundaries

- The integration may connect by serial, TCP, or UDP. A TCP broker can be an external bridge; it is not an integration runtime dependency and must not be started by this repository.
- Use the isolated Modbus simulator and static fixtures described in [`testing/README.md`](../../../external/Homeassistant-Growatt-Local-Modbus/testing/README.md) for repository-local dry runs. Any live DEV broker/HIL access remains outside the integration runtime and must be explicitly bounded and documented.
- The physical Modbus serial link has one master at a time. Do not run direct-serial HA polling alongside the broker polling the same inverter.
- Setup, reconfiguration, commissioning dashboards, and sensor discovery must remain read-only. Do not issue inverter writes as part of connection tests or sensor selection.
- Keep device identity based on the inverter serial number. A transport change must not silently repoint an existing config entry to a different inverter.
- Preserve existing entity IDs and recorder/statistics continuity when adding setup choices or changing register polling. Existing users must not lose entities through an implicit default change.
- The development HA staging dashboard lives in the HA-core wrapper, not in this integration package. Keep it optional and free of fixed production endpoints if it is generalized for reuse.

## Development workflow

- Review the relevant tests and validation documents before changing runtime behavior.
- For Home Assistant config flow or options changes, update translations and regenerate the English translation file as described in the HA-core `AGENTS.md`.
- Add focused tests for transport validation, serial-number identity checks, selected entity/register plans, and reload behavior.
- Run the integration tests and Home Assistant lint/validation required by the containing HA-core workspace.
- Do not commit, publish, or open a pull request without human review of the complete change.

## Raspberry Pi production boundary

The RPi update is a later, separately reviewed cutover. Follow the backup, compatibility, pre-cutover inventory, smoke-test, and rollback gates in [`HA-GII-6_PRODUCTION_UPGRADE_READINESS.md`](HA-GII-6_PRODUCTION_UPGRADE_READINESS.md). Do not infer production deployment authorization from development validation or from this roadmap.
