# Growatt Local HA integration roadmap

**Status snapshot:** 2026-09-20

**Scope:** the Growatt workstream within the wider home-energy and smart-charging project. It covers the `growatt_local` integration, the register-map handoff, and the Growatt production update on the Raspberry Pi (RPi). The cross-system plan is in the HA-core workspace [`ROADMAP.md`](../../../ROADMAP.md). This document does not authorize a production cutover.

## Current state

- The integration has an initial Home Assistant config flow for serial and network Modbus connections. The network path covers TCP and UDP. Device identification can select a supported device family or ask the user to choose when automatic identification is inconclusive.
- This is a custom integration, not currently part of Home Assistant Core. The communication API currently lives inside the integration component, and the manifest declares `pymodbus` directly.
- The runtime contains model-specific register maps, sensor/entity descriptions, and existing power-control entities. The runtime is smaller in scope than the broad research register specification; source documentation alone is not sufficient to expose a register.
- The sibling `growatt-inverter-info` repository has a canonical register specification at `../../../external/growatt-inverter-info/spec/growatt-register-spec.json` and a captured HA runtime snapshot at `../../../external/growatt-inverter-info/sources/runtime/ha-local-registers.snapshot.json`. The runtime snapshot provides correlation, but there is no enforced semantic parity check or reviewed promotion path from the canonical map into the integration runtime. Runtime dictionaries also have family-specific overlap and inheritance. See the canonical specification and provenance records in the sibling [`growatt-inverter-info`](../../../external/growatt-inverter-info) repository.
- The current sensor setup filters descriptions against registers available for the selected model, then adds all matching descriptions and schedules their registers for polling. There is no user selection of which sensors to expose or poll. The options flow does not currently change transport.
- There is no `reconfigure` flow yet. An existing entry cannot use the integration UI to move from broker-mediated TCP to direct serial while preserving its device identity.
- A separate DEV Home Assistant staging environment and Growatt dashboard have been added in the HA-core wrapper. The controller pins the config entry to broker DEV `192.168.1.148:5021`, sets inverter power control on, and enables control entities. Treat this staging setup as potentially write-capable engineering/HIL tooling, not as a read-only generic setup wizard. The bounded HA-GII-5 validation was a separate read-only run with power control off.
- Read-only HIL validation has been recorded for a MIN 6000TL-XH with ARK storage through the DEV TCP broker endpoint. The HA-GII-5 report accepted that bounded run with follow-ups; it did not change production HA, the production broker, or inverter settings. See [`HA-GII-5_DEV_HA_DEPLOYMENT_VALIDATION.md`](HA-GII-5_DEV_HA_DEPLOYMENT_VALIDATION.md).
- A production upgrade readiness review exists. It identifies outstanding pre-cutover gates, including a fresh verified full backup, production Core compatibility, a pre-cutover entity/statistics inventory, and a check of the reactive-power statistics metadata. The candidate reviewed there has not been deployed. See [`HA-GII-6_PRODUCTION_UPGRADE_READINESS.md`](HA-GII-6_PRODUCTION_UPGRADE_READINESS.md).
- The provisional cross-device EMS package now lives in the workspace project `../../external/home-energy-manager/`. This repository only owns Growatt Modbus setup, polling, entities, and Growatt-specific tests. Zoe charging-rate exploration exists in the sibling PyCanZE tools, but a next-day Zoe SoC/charge prediction model is not implemented yet.

## Recent TOU control work and broker dependency

The TL-XH integration now exposes all nine inverter time-of-use periods as
configurable Home Assistant controls: a priority selector, start and end time,
and enable switch for each period. Each change writes the complete two-register
period pair with Modbus FC10, preserves the other packed fields, serializes
concurrent writes, and verifies the device value after a cache-aware refresh.
The global AC-charge permission at H3049 remains a separate control and is not
duplicated per period.

The implementation is committed as `8ee0db8` (`Add configurable TL-XH TOU
controls`). The DEV staging HA instance registered all 36 controls. A live HIL
test changed the end time of disabled period 2 from 19:58 to 23:55, confirmed
the write/readback, and restored 19:58 while leaving the period disabled. The
full nested test suite passed 102 tests.

The current 11-second wait in the HA write path is a temporary workaround for
broker cache coherence. After a successful FC06 or FC10 write, the broker can
otherwise return the old value for the affected cached register block until its
normal refresh. The broker roadmap must therefore deliver a serialized
read-after-write of the complete affected block, using the actual device
response and committing the refreshed block atomically before acknowledging the
write. Remove the HA delay only after that broker behavior has tests for FC06,
FC10, concurrent readers, and failed readback.

## Product direction

Use Home Assistant's standard integration UI for setup and reconfiguration. After the device is identified, offer a clear, model-specific choice of relevant sensors. Keep setup in the integration flow. A separate DEV dashboard may expose explicitly labeled manual controls for supervised hardware-in-the-loop testing; it does not own or replace config-entry setup and must never be copied into production by the staging workflow.

The primary transport transition to support is broker-mediated TCP to direct serial. Both transports must retain the same inverter identity, and only one process may poll the physical serial link at a time.

## Work plan

### 1. Finish setup and transport reconfiguration

- Implement Home Assistant's config-entry `reconfigure` flow for the current transport and a replacement transport.
- Reuse connection validation and device-identification logic from initial setup.
- Read the inverter serial number before saving. Keep the current entry only when it is the same device; otherwise stop and direct the user to configure a separate device.
- Update and reload the entry only after a successful read-only connection check. On failure, retain the old working configuration.
- Cover serial, TCP, and UDP validation, transport changes, reloads, identity mismatch, and failure recovery with tests.

### 2. Reconcile and synchronize the register map

- Treat `growatt-inverter-info/spec/growatt-register-spec.json` as the canonical research specification and the integration's device-family register dictionaries/entity descriptions as the runtime implementation. Keep those roles explicit; the broad specification is not a runtime sensor list.
- Compare the canonical spec, the extracted runtime snapshot, and the integration implementation by model/family, table (holding/input), address, width, decoding, scale, sign, unit, and evidence/applicability. Start with the production MIN 6000TL-XH + ARK profile, then cover other supported families.
- Classify every difference as a reviewed runtime mapping, missing implementation, runtime-only compatibility mapping, inapplicable family record, unresolved conflict, or insufficient evidence. Preserve provenance and entity identity for accepted changes.
- Decide and document a sustainable synchronization mechanism: a parity validator and reviewed promotion workflow are required; generate runtime code only if model applicability and semantic conflicts can be represented safely. Do not promote research-only, conflicting, or unvalidated records automatically.
- For each accepted runtime change, update the register definitions, sensor/entity descriptions, translations, coordinator read plan, tests, and relevant reference snapshots together. Validate the canonical GII artifacts and the integration artifacts independently.
- Reconcile any required upstream integration changes before a substantial register redesign, preserving the fork's validated MIN/TL-XH corrections and stable public entity identities.

### 3. Add useful sensor selection and polling

- Build the choices from the detected model and registers the device actually supports.
- Group choices into understandable sets such as core power/energy, PV strings, grid, battery/storage, and diagnostics. Provide a sensible basic selection and an advanced way to opt into additional sensors.
- Persist choices in the config entry and allow users to change them later.
- Make the selected set govern both which entities Home Assistant exposes and which Modbus registers the coordinator requests. Include only required dependencies for derived/status entities; do not keep polling a register solely because a disabled entity description exists.
- Preserve the current entity and recorder behavior for existing config entries during migration. Do not silently remove or disable existing entities when introducing defaults for new entries.
- Test unsupported models/registers, selection persistence, selection changes, and the resulting request plan.

### 4. Keep the DEV dashboard useful for commissioning and manual tests

- Keep setup and transport selection in the integration's config flow.
- If the dashboard remains part of the deliverable, make it reusable for the configured Growatt device instead of hardcoding the DEV broker host, port, or one installation's entity IDs.
- Show connection/read health and selected sensor values. Keep commissioning separate from normal household dashboards. Mark every manual control with the DEV target and explain that it writes to the connected equipment; do not create or overwrite production dashboards.
- Document that it is a commissioning/diagnostic dashboard, not a prerequisite for normal integration use.

### 5. Validate the candidate before production

- Run focused unit/config-flow tests, translation checks, Home Assistant validation, and the relevant integration test suite.
- Validate setup, reconfiguration, sensor selection, reload, identity continuity, and absence of writes in disposable HA/simulator testing.
- Run bounded read-only checks against the DEV broker path, then separately conduct deliberate, supervised tests of supported manual controls and verify the equipment response. Check direct serial in a controlled test window. Never let HA and the broker poll the same inverter serial connection simultaneously.
- Validate TOU FC10 writes through the broker's read-after-write cache contract. Keep the current HA cache wait only as a temporary compatibility measure; remove it after the broker refreshes and atomically publishes the actual post-write block for FC06 and FC10, including concurrent-read and failed-readback cases.
- Confirm existing entity IDs, unique IDs, energy totals, device identity, and recorder/statistics behavior remain acceptable. Record unresolved findings rather than silently migrating history.

### 6. Update the RPi in a controlled cutover

- Reconcile the final candidate revision with the preconditions in HA-GII-6. In particular, establish production Core compatibility before installation.
- Create and verify a fresh full backup including Recorder data, configuration, `.storage`, and `share`; capture the current config-entry, entity, device, state, and statistics manifests.
- Decide whether production remains on the broker TCP connection or moves to direct serial. For a direct-serial move, establish device path/permissions and schedule a maintenance window that transfers sole serial ownership from the broker to Home Assistant.
- Stage and checksum the candidate, preserve the exact current integration for rollback, switch the installed source atomically, restart Home Assistant, and follow the HA-GII-6 smoke and rollback checks.
- Record the result and keep the previous integration revision and transport configuration recoverable until the post-cutover observation passes.

Production deployment is a distinct operation from implementing or testing these features. This roadmap is planning documentation, not cutover approval.

## Optional longer-term path: Home Assistant Core contribution

The note in the old README about a separate API repository applies specifically to preparing a Core contribution; it is not a prerequisite for continuing to run the integration as a custom component. Home Assistant's Core contribution guidance calls for a reusable Python communication library, and its dependency-transparency rule expects an OSI-licensed public package published on PyPI from a public CI pipeline and tagged public repository. The library would own Modbus/device communication; `growatt_local` would keep the Home Assistant config flow, entities, coordinator integration, and translations.

If Core inclusion is pursued:

- Extract and test the communication API as a reusable package, establish its public repository/release process, and declare the published library in the integration manifest.
- Audit the integration against the current Home Assistant Integration Quality Scale and complete every Bronze rule before proposing it as a new Core integration. Track the work in `quality_scale.yaml` and include tests, translations, end-user documentation, branding, and diagnostics as required by the rules.
- Update the manifest for Core conventions. The current manifest has a config flow but no explicit `integration_type`; Home Assistant requires that field for Core integrations with a config flow.
- Check product eligibility, prepare the Home Assistant documentation page, and submit the Core contribution for review. Meeting the checklist makes it eligible for review; it does not guarantee acceptance.

This optional Core path is independent of the RPi operational cutover. Keep the RPi on the reviewed custom integration until a Core release is accepted and provides a practical migration path.

## Completion criteria

The integration is ready for the planned RPi update when:

1. Initial setup and reconfiguration use the standard HA UI, validate the selected transport, and preserve the same inverter identity across TCP/serial changes.
2. A reviewed parity report explains canonical-spec/runtime differences for supported models, and an automated check protects the agreed synchronization boundary.
3. Users can choose model-supported sensors, change those choices later, and the chosen set controls both entity exposure and register polling.
4. Existing entity IDs and cumulative energy/statistics remain continuous for current users.
5. Automated tests, bounded read-only checks, and supervised DEV manual-control tests pass. Connection validation stays read-only, and there are no concurrent serial masters.
6. The HA-GII-6 pre-cutover gates are satisfied and the exact candidate, backup, cutover, smoke checks, and rollback path are recorded.
