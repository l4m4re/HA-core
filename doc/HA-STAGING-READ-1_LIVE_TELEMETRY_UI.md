# HA-STAGING-READ-1 — live telemetry staging UI

Status: `HA_STAGING_READ_UI_ACCEPTED_WITH_FOLLOW_UP`

This report records the controlled development Home Assistant staging
deployment against the live Growatt inverter.  The staging UI is read-focused,
but the staging runtime is deliberately in `HIL_CONTROL` with full Growatt
write access enabled, following the explicit operator instruction for this
session.  No write was issued by this work.

## Revisions and runtime

- HA-core starting revision: `a16c431c44ff9865c81fa05a7344b7292c093439`
- Growatt integration source: `8b05113cedb586f43b4761ebf50a3a1fa7dada3`
- Live broker source/image: `61dbb16625fce63bdce7da97db85de3f693ecf1a`,
  `growatt-rtu-broker:broker-4-tcp-writes-all-61dbb16`
- Staging endpoint: `192.168.1.148:5021`, Modbus unit `1`
- Staging integration type: `hybrid_120_TL_XH`, model `MIN 6000TL-XH`
- Staging URL: `http://localhost:8123`
- Staging mode: `HIL_CONTROL`, `control_armed: true`

The production HA configuration was not modified.  The existing live broker
was not restarted or reconfigured.  Existing research directories and raw
logs remain untouched.

The staging process is persistent under `.staging/ha-config`; its current
status reports `running: true`.  The browser endpoint currently presents the
normal Home Assistant onboarding page until a staging administrator completes
the local onboarding flow.  After that, the sidebar contains the generated
`Growatt Staging` dashboard at the configured `growatt-staging` path.

## UI and entity contract

The generated source dashboard is `script/ha_staging_dashboard.json`.  It is
bounded to four views: overview, battery, energy, and diagnostics.  It has 58
entity references, all of which exist in the staging entity registry.  It does
not add guessed cell channels or duplicate physical entities, and it does not
change existing entity IDs or unique IDs.

The staging registry contains 677 total entries, including 96 Growatt entries
(94 sensors and 2 switches).  The existing public entity surface was retained;
the dashboard is an additional presentation layer rather than a migration.

### Present and suitable for the staging UI

The following groups are backed by the reconciled MIN/TL-XH read mapping and
were observed through the live path:

- PV input/output power, voltage, current, daily and total energy;
- load, grid import/export, power-to-user, and battery charge/discharge power;
- battery SOC, voltage, BDC current, BMS current and BMS voltage;
- validated BMS cell-voltage extrema and their reported cell indices
  (`I3230`/`I3231`), without inventing individual cell entities;
- cumulative production, input, grid and user energy counters;
- inverter status, status code, fault and warning diagnostics;
- current XH operating priority feedback.

The latest observed staging values included approximately 422.9 W PV output,
451 W user load, 39% SOC, 209.56 V battery voltage, 2.1 A BDC battery
current, -2.2 A BMS battery current, 3.262–3.265 V cell extrema, and 19625.8
kWh total produced energy.  These are live observations, not fixed fixtures.

### Deliberately not promoted as established semantics

- Individual battery-cell channels beyond the validated extrema.
- The unresolved BMS temperature interpretations associated with `I3191`,
  `I3194`, and `I3195`; existing legacy entities remain visible in the registry
  but are not presented as trusted values on the new dashboard.
- A successful XH schedule decoder: the existing schedule entity currently
  reports `unknown`, so it is shown as an unresolved feedback surface.
- Broker cache-health counters: the current broker logs cache events, but does
  not expose a stable HA diagnostic entity for them.

Raw warning/fault/status codes, BMS status bits, cell indices, and similar
values are diagnostic-only and are not treated as user-facing energy
quantities.

## Raw-to-browser validation

The active broker log showed complete, CRC-valid Shine requests and responses,
including:

- FC20 request `start=0,count=100` served from the FC20 cache;
- FC03 native holding pages `0,count=125` and `3000,count=125`;
- FC04 native input page `3000,count=125`;
- predictive prefetch of the same native pages before the Shine request;
- physical refresh timing of roughly one vendor-paced transaction per second,
  followed by cache service to the Shine and HA clients.

The staging HA log showed repeated successful fetches from `:5021`, including
the first live fetch and subsequent one-minute updates.  The resulting states
and metadata match the existing integration contract: power sensors retain
`W` and `device_class: power`, voltage/current sensors retain their physical
units and classes, and cumulative energy sensors retain `kWh`, energy state
class, and total-increasing counter semantics where already established.

The current priority entity retains its existing identity and exposes the
decoded `load_first` value with raw-value and validity attributes.  The XH
schedule remains explicitly unresolved rather than being presented as valid.

## Read plan and cache behavior

The integration continues to use the family-specific MIN/TL-XH native pages:

- FC04: `3000..3124` and `3125..3249` for fast telemetry;
- FC03: `3000..3124` for control/static feedback and `0..124` for static data;
- FC04: `3250..3374` for diagnostic coverage when needed;
- FC20: the existing broker-specific cached/prefetched path.

This keeps the bus transaction-oriented: useful values are decoded locally
from complete native blocks instead of being fetched one register at a time.
The logs confirm that Shine requests are still accepted and returned, while
the broker opportunistically refreshes stale pages.  Occasional physical
refresh timeouts remain visible in the broker logs, but later refreshes and
staging HA fetches succeeded; this is a follow-up for transport-health
instrumentation, not a reason to hide failures.

## Write state and safety boundary

At the explicit operator request, staging is not in `HIL_READ`.  It is armed
as `HIL_CONTROL`, and the Growatt write entities are enabled.  The deployed
broker also has TCP FC06/FC10 write forwarding enabled for both production and
development TCP clients.  This report records configuration only: no staging,
broker, Shine, inverter, or portal write was performed while completing this
UI task.

The new dashboard intentionally remains read-oriented so that normal telemetry
inspection does not accidentally invoke a control action.  Any later write
test must be treated as a separate, explicitly requested HIL operation.

## Follow-up items

1. Complete local staging onboarding and verify the four dashboard views in a
   browser.
2. Export broker cache age/hit/miss/timeout health as a bounded diagnostic
   surface instead of relying only on broker logs.
3. Reconcile the unresolved XH schedule readback and BMS temperature fields.
4. Review the existing Recorder warning that reactive power currently conflicts
   with previously compiled statistics using `W` versus `var`; do not silently
   rewrite historical statistics.
5. Keep production HA and the live write-enabled broker running unchanged until
   a separately reviewed migration or write-validation task is approved.

No HA-GII-5 write test or production upgrade was started by this task.
