# HA-DEV-1R clone and upgrade-rehearsal procedure

This procedure is intentionally bounded to a disposable copy. It must not be
run against `/config` on the live Home Assistant host.

## Inputs

1. Create a normal Supervisor full backup and export it outside Git.
2. Create a consistent Recorder copy using SQLite's online backup API.
3. Extract the Home Assistant archive to a temporary DEV directory.
4. Preserve the `share/custom_components/Homeassistant-Growatt-Local-Modbus`
   source outside Git when the production integration is a symlink.

The HA-DEV-1R run used `/tmp/HA-dev-1R-20260906/` and retained the backup,
Recorder copy, production clone, credentials, and quarantine there.

## Quarantine

Run:

```bash
python3 script/ha_dev_clone.py quarantine /tmp/HA-dev-1R-20260906/dev-config/data
python3 script/ha_dev_clone.py validate /tmp/HA-dev-1R-20260906/dev-config/data
```

The script preserves the production YAML, config-entry store, and auth files
inside `.ha-dev-quarantine/`. On the disposable copy it disables every copied
config entry, replaces action-capable YAML with a safe overlay, and creates a
fresh DEV onboarding boundary. It does not delete production data or mutate
the production host. The original auth/config data remains recoverable in the
quarantine directory.

Complete the DEV onboarding with a new local admin. Store the credential file
outside Git with mode 600; do not copy production auth or secrets into a
shared development environment.

## Read-only Growatt baseline

On the DEV copy only, enable the existing `growatt_local` entry and change its
endpoint port from production port 5020 to broker port 5021. Keep unit 1,
address 1, and `inverter_power_control: false`. Start HA Core with:

```bash
python3 -u -m homeassistant \
  --config /tmp/HA-dev-1R-20260906/dev-config/data \
  --skip-pip --log-no-color
```

Verify the frontend, config entry state, selected telemetry, entity IDs,
units/classes, Recorder startup, and Energy storage. Confirm the Modbus log
contains reads only (FC03/FC04); do not call control services.

## Candidate comparison

Before the second boot, move the exact production component into the
quarantine directory and copy the candidate component into the DEV clone:

```text
production clone/custom_components/growatt_local
  -> .ha-dev-quarantine/growatt_local-production
workspace external/Homeassistant-Growatt-Local-Modbus/custom_components/growatt_local
  -> production clone/custom_components/growatt_local
```

Repeat the same read-only checks and compare the saved entity IDs, unique IDs,
classes, units, representative values, and error classes. Leave the DEV
frontend running only if its temporary port and credentials are clearly
isolated from production.

## Guardrails

Do not run `git clean`, do not create a second worktree, do not change the
production config, do not upgrade production, and do not issue Growatt,
Peblar, or Zoe writes. A future entity source migration requires a reviewed
old/new semantic and cumulative-counter continuity test.
