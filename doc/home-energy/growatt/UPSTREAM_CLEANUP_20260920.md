# Growatt repository ownership cleanup

This record explains the local-only material removed from the Growatt
integration on `maintenance/upstream-cleanup-20260920`.

## Keep in the integration repository

- `custom_components/growatt_local/`: the runtime integration, including the
  model-specific register dictionaries, decoding, polling, entities,
  translations, and TOU controls.
- `tests/`, `testing/`, `pytest.ini`, and `requirements_dev.txt`: focused
  integration and simulator checks that protect the runtime behavior.
- `.github/workflows/`: CI and release automation useful to the integration
  repository.
- `doc/GROWATT_RUNTIME_REGISTER_AUDIT.md`, `doc/HA-7A_MIN_RUNTIME_AUDIT.md`,
  and `doc/HA-7C_MIN_NATIVE_BLOCK_POLLING.md`: runtime and polling reports that
  explain the implementation under review.
- `README.md` and `doc/README.md`: user and contributor instructions for the
  integration and its simulator.

## Move out of the integration repository

- The provider-neutral `ems_contract/`, `custom_components/ems_shadow/`, EMS
  fixtures, EMS tests, and HA-8A through HA-8D documents now live in
  `external/home-energy-manager/`. They are staging-project code, not Growatt
  integration code. The workspace staging controller points to that location.
- HA-GII validation reports and their structured evidence now live in
  `doc/home-energy/growatt/`. They are local HIL and production-readiness
  records, useful for the workspace but not part of the reusable integration
  package.

## Remove from the integration repository

The former `doc/` register pipeline was a second copy of the research corpus:
source snapshots, overlays, graph exports, generated references, family
Markdown, extraction scripts, and their validators. GII now owns that
material under `sources/`, `spec/`, and `docs/`. The integration retains only
the runtime mapping and its focused implementation reports; future register
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
is the runtime integration, its focused tests, reproducible simulator helpers,
and documentation needed to use or review those changes.
