# Growatt repository ownership cleanup

This record explains the local-only material removed from the Growatt
integration on `maintenance/upstream-cleanup-20260920`.

## Keep in the integration repository

- `custom_components/growatt_local/`: the runtime integration, including the
  model-specific register dictionaries, decoding, polling, entities,
  translations, and TOU controls.
- `tests/`, `testing/`, `pytest.ini`, and `requirements_dev.txt`: focused
  integration checks and the direct register reader that protect or diagnose
  the runtime behavior.
- `.github/workflows/`: CI and release automation useful to the integration
  repository.
- `README.md` and `doc/README.md`: user and contributor instructions for the
  integration runtime.

## Move out of the integration repository

- The provider-neutral `ems_contract/`, `custom_components/ems_shadow/`, EMS
  fixtures, EMS tests, and HA-8A through HA-8D documents now live in
  `external/home-energy-manager/`. They are staging-project code, not Growatt
  integration code. The workspace staging controller points to that location.
- HA-GII validation reports and their structured evidence now live in
  `doc/home-energy/growatt/`. They are local HIL and production-readiness
  records, useful for the workspace but not part of the reusable integration
  package.
- Runtime register audits and polling-plan reviews now live in the GII
  repository under `docs/consolidation/`, alongside the evidence and reviewed
  register specification.
- The Modbus simulator, dataset builders, capture compactor, probe utilities,
  mutation examples, and simulator launch scripts now live in the
  `growatt-rtu-broker` repository. The integration tests may consume that
  broker-owned simulator as development infrastructure, but the simulator is
  not part of the integration package.

## Remove from the integration repository

The former `doc/` register pipeline was a second copy of the research corpus:
source snapshots, overlays, graph exports, generated references, family
Markdown, extraction scripts, and their validators. GII now owns that
material under `sources/`, `spec/`, and `docs/`. The integration retains only
the runtime mapping and focused implementation tests; future register
knowledge follows the GII review workflow.

The old `homeassistant/` package contained minimal stubs that shadow the real
Home Assistant package and made standalone test results misleading. The
development requirements already provide Home Assistant, so the stubs were
removed. The old `testing/growatt_registers.md` parser pair was removed with
the duplicate register map; simulator dataset provenance belongs with the
broker project.

## Upstream review boundary

Before opening an upstream pull request, review the remaining diff against
`upstream/master`. Project roadmaps, HIL records, workspace staging code, and
EMS files must stay outside that pull request. The expected upstream content
is the runtime integration, its focused tests, and documentation needed to use
or review those changes. Simulator infrastructure remains in the broker
repository.

## Remaining branch-only inventory

Against the fetched `upstream/master`, 24 tracked files remain in the
integration branch:

- Runtime additions: `custom_components/growatt_local/API/__init__.py`,
  `ems_types.py`, `select.py`, `time.py`, and `tou.py`.
- Integration documentation and developer entry points: `doc/README.md`,
  `testing/README.md`, `testing/read_registers.py`, `pytest.ini`,
  `requirements_dev.txt`, and `.github/workflows/ci.yml`.
- Focused tests: `tests/conftest.py`, `tests/test_config_flow.py`,
  `tests/test_growatt_api_read_write.py`, `tests/test_ha5_regressions.py`,
  `tests/test_ha_gii2_decoder.py`, `tests/test_ha_gii3_metadata.py`,
  `tests/test_native_block_polling.py`, `tests/test_sensor.py`,
  `tests/test_sensor_key_uniqueness.py`, `tests/test_status_semantics.py`,
  `tests/test_tou_controls.py`, `tests/test_unique_sensor_ids.py`, and
  `tests/__init__.py`.

These files are the remaining candidates for an upstream review. The first
group changes runtime behavior; the latter groups make that behavior
reproducible and reviewable. No simulator, register-research corpus, EMS
project code, or HIL report remains in the integration repository.
