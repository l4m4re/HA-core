# DEV manual-control test plan

## Scope

Run the first physical control checks only from the DEV Home Assistant at
`http://localhost:8123`, using the **Manual DEV control** view. Growatt is
pinned to the DEV broker at `192.168.1.148:5021`, unit 1. The EMS planner must
remain disconnected from every actuator. Do not use the live Home Assistant or
the production Growatt endpoint for these checks.

These are attended hardware-in-the-loop (HIL) tests. Before each test, confirm
that the dashboard is the staging instance, the target is the expected DEV
device, and every relevant input is available and recent. Stop immediately if
the DEV endpoint or device identity is unclear, any control or feedback entity
is stale/unavailable, a vehicle is connected unexpectedly, or observed power
changes unexpectedly. Record the starting value, requested action, resulting
entity value, device response, and restoration.

The DEV Home Assistant is a separate control instance, but these dashboard
controls write to the connected physical charger and inverter; DEV is not a
hardware simulator. The EMS input snapshot refreshes every 30 seconds, and
the manual view recalculates Peblar report ages every minute.

The native Peblar switch simulation passed with
`uv run --no-sync pytest -p no:homeassistant -q tests/components/peblar/test_switch.py`
(`11 passed`, four snapshots). It verifies the switch's mocked API calls,
including zero current on turn-off and the fixture's 16 A limit on turn-on.
The DEV control round trip below now has fresh Peblar entity feedback. It
confirms the integration accepted both switch actions and restored the
reported charge state and limit. Since no vehicle was connected, it does not
verify vehicle charging or solar-only behavior.

## First test: Peblar charge-enable round trip with no vehicle connected (completed)

The latest DEV EMS input snapshot at 2026-09-17 23:37:32 UTC reported Peblar `no_ev_connected`, 0 W, charge enabled, a 28 A limit, and `scheduled` mode. Peblar state, power, charge-enable, and limit reports were 9.4 seconds old; mode was 249.7 seconds old, within the six-minute limit. Growatt and Zonneplan were available; Growatt AC Charge was off and Power control on, both reported 59.7 seconds earlier. Zoe live SoC is not configured, so overall EMS input status remains incomplete; the planner is `shadow_only` and not connected to actuators. The input sensor exposes `snapshot_updated_at`; the dashboard gate requires an EMS snapshot no older than 45 seconds and each control input to meet its own age limit.

On 2026-09-18 at about 07:20 UTC, the DEV input snapshot passed preflight: Peblar was `no_ev_connected`, 0 W, charge on at 28 A in `scheduled` mode; its main reports were 7.5 seconds old and mode was 98 seconds old. Growatt AC Charge was off. The snapshot was 25 seconds old. The switch reported off after `switch.turn_off`, then on after `switch.turn_on`. The first EMS snapshot lagged the switch briefly; fresh feedback at 07:22:11 UTC confirmed charge on at 28 A, `scheduled`, `no_ev_connected`, and 0 W. Physical operator presence and competing-client status were not independently recorded. Zoe live SoC remains unconfigured, so overall EMS input status is incomplete; the planner remains shadow-only and disconnected from actuators.
Preconditions:

1. Peblar status is `no_ev_connected` and power is 0 W.
2. Its charger status, power, charge-enable switch, and current-limit number
   have reports no more than 60 seconds old.
3. Note the current limit and smart-charging mode. The Peblar integration polls
   mode every five minutes; if its report is more than six minutes old, confirm
   the mode on the charger. Do not change it.
4. No EMS automation or other client is controlling Peblar.

Actions and expected feedback:

1. Turn **Peblar Charge** off. The integration sends a zero current limit to
   the charger. Expect the charge switch to report off; the number entity can
   retain its last nonzero limit because values below 6 A are intentionally
   omitted from that entity.
2. Confirm Peblar remains `no_ev_connected` at 0 W.
3. Turn **Peblar Charge** on. The integration restores the previous known
   charge limit, expected to be 28 A if unchanged since preflight.
4. Confirm the switch is on, the limit has returned to its recorded value,
   Peblar remains `no_ev_connected`, and power remains 0 W.

If feedback does not match, stop and use the charger itself to restore the
recorded state. Do not continue to Growatt tests until the cause is understood.

## Solar charging follow-up

**Control design:** keep Peblar in normal direct-charging mode (`default`) and
use Growatt's independent inverter meter over local RS485/Modbus for import and
export feedback. The user reports this link is reliable. The P1 meters have had
issues since the Zonneplan P1 meter was connected at the inverter output, so P1
is not a controller input. Peblar has no household meter of its own.

The 85% target and fixed 3,500 W discharge cap below apply only to this
attended weekend solar-charging trial. There is not yet a time-based battery
SoC schedule or a nightly planner, and this test does not configure Growatt TOU
windows. The future EMS should plan time-indexed battery targets and EV charge
goals from prices, PV and load forecasts, battery reserve, and departure
requirements; verify Growatt TOU limits and read-back before any TOU control is
enabled.

The intended home-battery target is about 85%, within an 80–90% band. The DEV
automation starts only after fresh Growatt SoC is above 90%. It sets the Peblar
current limit to 6 A while off, selects `default`, and starts charging. Once
charging, it adjusts current in 1 A steps no more often than once per minute.
For this solar HIL trial, cap Growatt battery discharge at a fixed 3,500 W and
leave 300 W of headroom before raising the Peblar limit. Reduce current above
3,500 W discharge, above 400 W Growatt import, or when SoC is at most 85% and
discharge exceeds 200 W. Increase above 85% when import is below 100 W; export
or battery charge above 800 W can also raise current at SoC of at least 85%.
These are initial trial thresholds. The controller runs Friday through Sunday
only.

A register-based cap was investigated but is not used: the candidate holding
register for Active P Rate read 100%, while the candidate Output Max Power
Limit field read 0 W. Neither represented the expected 70% / 4,200 W limit,
so the trial uses the user-selected fixed 3,500 W cap.

The relay stays on through ordinary surplus changes; current is modulated to
avoid contactor cycling. If SoC falls below 80%, lower current to 6 A; if it
remains below 80% at that minimum, stop charging and wait until SoC rises above
90% before restarting at 6 A. This safety pause overrides the preferred
15-minute minimum run. Stale telemetry, EV disconnect, Growatt AC Charge being
on, or a manual stop also stops the test. The charger can become full; Zoe SoC
is not required.

Use Growatt `Power to user` and `Power to grid` as the controller's import and
export channels; verify their direction during the next charging period. The
Growatt meter already includes Peblar in its flow, so do not add Peblar power
again to calculate net household flow. Use Growatt PV/load, battery
charge/discharge, and Peblar power/current for cross-checking. Keep AC Charge
off during the trial.

At 08:56 UTC on 2026-09-18, DEV reported Growatt SoC 92%, AC Charge off,
battery charge power 1,626 W, and battery discharge 0 W. Peblar was charging in
`default`, at a 7 A limit and 1,437 W. On the preceding poll, battery
discharge was about 1,360 W while Peblar was at 8 A; the limit then stepped
down to 7 A. At 08:58 UTC, SoC was 93%, Peblar had ramped to 9 A / 1,896 W,
and Growatt battery charge/discharge were 53 W / 94 W. This was an observed
control response in both directions. Later the original rule ramped Peblar to
20 A / about 4.5 kW; Growatt reported about 3.65 kW battery discharge, and the
user judged import likely. The test was paused with Peblar off at a 6 A limit.

After the DEV HA restart at about 09:31 UTC, the test was re-armed. At 09:34
UTC it remained armed through a controller cycle: Growatt SoC was 89%, battery
charge was 391 W and discharge 0 W, Growatt AC Charge was off, and Peblar was
`suspended` at 0 W with a 6 A limit in `default` mode. Charging remains off
until SoC rises above 90%. The new 3,500 W cap is loaded but has not yet been
re-tested under charging. Keep the trial attended and record the next current
changes and meter response.
The earlier switch test at 07:20–07:22 UTC was only an entity-feedback round
trip with no vehicle connected. It did not test EV charging or solar-following
behavior. Keep the new test attended in DEV and record SoC, meter power, battery
power, Peblar limit and power, and each state change.

## Growatt tests

The first test does not enable **AC Charge**: turning it on may begin drawing
grid power to charge the battery. Keep it off until there is an attended test
window with a deliberate duration and a clear stop condition. Any later AC
charge test must record the starting state of charge and charge power, confirm
that only the DEV broker is connected, observe charge power while enabled, and
turn AC Charge off immediately after the bounded observation.

Do not toggle **Power control** during this initial test. Its register controls
inverter power-control behavior, so first confirm the entity's exact effect
and arrange a separate observation window before changing it.

## Test record

| Field | Result |
| --- | --- |
| Date/time and operator present | 2026-09-18 07:20–07:22 UTC; command issued in the interactive DEV session; physical presence was not independently recorded |
| Staging instance and DEV target confirmed | `http://localhost:8123`; DEV Peblar control entity responded to both commands |
| Preflight values and freshness | Snapshot age 25 s; `no_ev_connected`, 0 W, charge on at 28 A, `scheduled` (user confirms 02:00–06:00 schedule); Peblar reports 7.5 s old, mode 98 s old; Growatt AC Charge off, 28 s old |
| Peblar off command and response | DEV `switch.turn_off`; charge switch reported off |
| Peblar on command and response | DEV `switch.turn_on`; charge switch reported on |
| Charger remained disconnected / 0 W | Fresh final DEV snapshot at 07:22:11 UTC reported `no_ev_connected` and 0 W |
| Final state restored | Confirmed on, 28 A, `scheduled`, `no_ev_connected`, 0 W in fresh DEV feedback |
| Unexpected behavior or follow-up | EMS snapshot briefly lagged the switch command; waited for fresh feedback before confirming restoration. The 02:00–06:00 schedule and `scheduled` mode were unchanged. Competing-client status and physical presence were not independently verified. No vehicle was connected, so solar charging itself was not tested. |
