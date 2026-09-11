# HA-STAGING-1: persistent full-energy HIL environment

Status: `HA_STAGING_FULL_HIL_ACCEPTED_WITH_FOLLOW_UP`

This document describes the persistent Home Assistant staging instance built
in the HA Core devcontainer. It is a development and HIL environment; it is
not a production migration and it does not change the live Home Assistant.

## Result

The staging instance is running from a persistent, repository-local state
directory:

```text
/workspaces/HA-core/.staging/ha-config
```

The browser endpoint is `http://localhost:8123`. A request to `/` redirects
to the normal fresh HA onboarding page and `/manifest.json` returns HTTP 200.
The visible HA name is `Home Assistant STAGING`; the devcontainer forwards
port 8123 with the label `Home Assistant STAGING`.

The initial sync was made from the existing production snapshot:

```text
/tmp/HA-dev-1R-20260906/production-config/data
```

The current staging process is in armed `HIL_CONTROL` mode. It successfully loaded the
workspace Growatt integration and established read traffic through
`192.168.1.148:5021`, unit 1. No Growatt write was performed by this task.

## Architecture and separation

```text
browser
   |
   v
HA staging :8123
   |-- Growatt integration (workspace source) -> broker DEV :5021 -> inverter
   |-- Zoe/PyCanZE telemetry integration point
   |-- Peblar Business 22 kW integration/control point
   |-- Zonneplan price/forecast integration point
   `-- future EMS and safety gate
```

The staging configuration is copied into `.staging/ha-config` and is the only
configuration opened by the staging HA process. The source snapshot is kept
at `.staging/source-snapshot` for reproducible refreshes. HA may migrate or
write the staging copy; it never opens the production `/config` or its
Recorder database. `.staging/` is ignored by Git.

Production authentication and other identity-bearing storage are removed from
the staging copy so the browser starts with a separate onboarding flow. The
production YAML files are retained under `.ha-staging-source` for inspection,
while staging runs with generated safe YAML rather than executing copied
production automations.

The production structure is materially reproduced in the copied `.storage`
state: entity/device registries, areas, helpers, Lovelace state, themes,
blueprints, config entries and the Recorder snapshot are available for
inspection. The cloned Recorder database is staging-owned and can be reset or
replaced without touching production.

## Operating modes

`script/ha-staging` is the deterministic control surface:

| Mode | Live reads | Real control writes | Purpose |
| --- | --- | --- | --- |
| `SHADOW` | optional | blocked | UI, replay, configuration and statistics work |
| `HIL_READ` | enabled | blocked | normal live telemetry development |
| `HIL_CONTROL` | enabled | allowed while armed | single-writer HIL testing |

The current staging Growatt entry is forced to:

```text
host     192.168.1.148
port     5021
unit     1
power control false unless HIL_CONTROL
```

The deployed broker's DEV TCP listener has write support enabled by default
(`DEV_TCP_WRITES=enabled`), as required by the existing BROKER-4A deployment.
Staging therefore keeps its own mode gate in front of that listener instead of
adding another broker-side write lock.

In addition, the workspace Growatt coordinator receives the staging state-file
path through `HA_STAGING_STATE_FILE`. Before any `write_register()` call it
requires armed `HIL_CONTROL`. This covers storage-register controls as well as
the optional inverter-power control entities; setting one config flag alone
would not be sufficient.

The safety layer rejects a staging start if a Growatt entry points at port
5020 or if HIL_CONTROL is unarmed. Sync creates the default armed
HIL_CONTROL state; a manual transition to HIL_CONTROL requires the literal
arm phrase shown below.

## Single-writer and fail-safe behavior

The current installation assumes one active writer. It does not implement
distributed writer arbitration or a lease service. `HIL_CONTROL` is an
explicit arming flag only. Stopping staging always downgrades it to
`HIL_READ`, including when the HA process is already absent. The broker
remains the lower-level source tag for Growatt traffic (`DEV_TCP`).

Production automations and control integrations are disabled in the staging
config entry store for the initial build. The control domains quarantined by
the override are `localtuya`, `rpi_gpio_pwm`, `rpi_power`, `shelly` and `tuya`.
This prevents copied production commands from competing with staging. The
single-writer assumption is explicit and is sufficient for the current setup.

The control model is deliberately fail-closed. It does not invent a new
unsafe fallback command for the inverter or wallbox. The next actuator task
must define the safe independent wallbox policy and any Growatt strategy
restoration/read-back required after a failed HIL session.

## Existing energy-system integration points

The production inventory shows one Zoe-related Energy entity,
`sensor.zoef_energy`, supplied through the existing Shelly/Zoe path. No
separate PyCanZE acquisition service was started by this task. The staging
design therefore treats the existing car-side poller/telemetry bus as the
authoritative future input and leaves command topics/actions separate from
telemetry. A second independent OBD poller should not be added.

No confirmed Peblar integration is present in the production inventory. The
staging architecture reserves the monitoring and control boundary for the
actual local Peblar Business 22 kW interface once identified. Reads can later
be shared or cached; commands must use the same staging mode gate as Growatt.

Zonneplan is not installed or configured in the production inventory. Its
future adapter belongs on the information side of staging and should expose
current/future tariff intervals with Europe/Amsterdam-aware timestamps. It
must share/cache upstream price data where possible and must not become an
actuator path.

These are explicit integration points, not claims that the three unfinished
integrations are already operational.

## Time, telemetry and Recorder

The generated staging configuration uses the production timezone:

```yaml
homeassistant:
  time_zone: Europe/Amsterdam
```

The staging Recorder opens the copied production snapshot under the staging
directory and can migrate it independently. This permits Energy Dashboard,
history and statistics inspection while preserving production entity IDs and
long-term-statistics context. A fresh staging Recorder can be created with
`reset-recorder`; production Recorder files are never selected by that
command.

Future EMS work must correlate source timestamps and freshness explicitly:
Growatt broker time, Zoe telemetry time, Peblar time and Zonneplan interval
boundaries. Stale Growatt or missing Zoe/Peblar inputs must be inputs to the
EMS safety decision, not silently substituted values.

## Workflow

From the repository root:

```bash
# Refresh the persistent staging copy from a production snapshot.
script/ha-staging sync /tmp/HA-dev-1R-20260906/production-config/data

# Start the browser-accessible staging instance.
script/ha-staging start
script/ha-staging status
tail -f .staging/home-assistant.log
# Open http://localhost:8123 in the browser.

# Safe modes.
script/ha-staging mode SHADOW
script/ha-staging mode HIL_READ

# Re-arm HIL_CONTROL after a safe-mode session.
script/ha-staging mode HIL_CONTROL --arm I_UNDERSTAND_REAL_HARDWARE

# Stop and return to a safe mode.
script/ha-staging stop
script/ha-staging restart

# Remove only the staging Recorder files.
script/ha-staging reset-recorder
```

The sync command is intentionally destructive only within `.staging/`: it
replaces the staging copy and source snapshot, never a user-selected broad
directory. It must not be given the live `/config` path without first making a
read-only snapshot.

## Startup assertions

Before launching HA, the controller verifies that:

* the staging directory exists and is not `/config`;
* the generated staging YAML contains no production Growatt port 5020;
* a Growatt entry exists and is pinned to `192.168.1.148:5021`;
* Growatt power control is false outside HIL_CONTROL;
* HIL_CONTROL is explicitly armed;
* control-domain entries are disabled by the staging override;
* sensitive production authentication storage is not reused.

The mode and endpoint are printed by the command-line controller and retained
in `.staging/state.json`. The staging HA log is at
`.staging/home-assistant.log` and is intentionally not committed.

## Validation performed

The following checks passed:

* Python compilation of `script/ha_staging.py`;
* shell syntax validation of `script/ha-staging`;
* Ruff check and format check for the new Python controller;
* persistent staging status reports armed `HIL_CONTROL`;
* HA root endpoint returns 302 to onboarding;
* HA `manifest.json` returns HTTP 200;
* staging HA initialized and loaded Growatt through `192.168.1.148:5021`;
* FC03/FC04 read traffic completed successfully in the staging log;
* the copied Recorder database migrated in the staging directory only.

Expected devcontainer-only warnings remain for unavailable Supervisor/USB/
Bluetooth/cloud services and the absent MQTT DNS name. They do not prevent
the staging HA browser endpoint or the Growatt HIL read path from starting.

## Follow-up before full HIL acceptance

The environment is accepted as the persistent staging foundation, with these
bounded follow-ups:

1. Create the separate staging administrator through the browser onboarding.
2. Inspect and connect the authoritative Zoe/PyCanZE telemetry bus without a
   duplicate OBD poller.
3. identify and implement the Peblar local read/control adapter, including
   source-attributed commands and the same staging mode gate.
4. Add or connect the Zonneplan price adapter with interval/DST tests and
   shared-cache/rate-limit handling.
5. Add replay fixtures and unit tests for the four progression levels:
   unit, replay, HIL_READ and armed HIL_CONTROL.
6. Exercise HIL_CONTROL with a separately reviewed, bounded write test and
   verify read-back, crash handling and safe strategy recovery.

No real Growatt, Peblar, Zoe or production HA configuration was changed by
HA-STAGING-1, and no Growatt write was issued.
