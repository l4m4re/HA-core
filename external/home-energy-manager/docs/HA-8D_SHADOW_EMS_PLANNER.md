# HA-8D quarter-hour shadow EMS planner

Date: 2026-09-06

HA-8D adds a pure, deterministic shadow planner. It consumes normalized
Growatt/P1 observations and quarter-hour prices, explains a hypothetical plan,
and produces no Modbus frame, Home Assistant service call, EV command, or
production deployment.

## Checkpoint and safety

This branch starts at HA-8C `63eaac8dda7665e3a3a2cc36b0e7d03eff06abbb`.
Existing HA production sensor/statistics identities remain untouched. The
untracked `doc/growatt_web/` research remains preserved.

The planner lives in `ems_contract/`, not in the Growatt integration.
The CLI's default mode reads only local JSON fixtures. It has no network client
and no actuator dependency.

## Zonneplan provider evidence

The inspected upstream stable tag is `2026.8.1`, commit
`5ff0e79295aee1a00d0fcaac23c364778e1e8e44`, from
[fsaris/home-assistant-zonneplan-one](https://github.com/fsaris/home-assistant-zonneplan-one).
The upstream source exposes:

```text
sensor.zonneplan_current_quarter_hourly_electricity_tariff
```

Its `forecast` attribute contains quarter-hour records with `start_date`,
`end_date`, `price_tax_included.amount`, and `price_tax_excluded.amount`.
Amounts are fixed-point integers divided by `10,000,000`. The upstream sensor
uses the tax-included amount as EUR/kWh and normalizes API timestamps into
Europe/Amsterdam. Forecast length is not fixed; the upstream README explicitly
says that Zonneplan does not deliver a constant set of forecast values. The tag
did not contain a dedicated forecast schema test suite, so HA-8D adds sanitized
adapter fixtures and tests.

The adapter in `ems_contract/zonneplan.py` requires timezone-aware quarter-hour
records, rejects gaps/overlaps/malformed records, and preserves tax-included
and tax-excluded values. The tax-included value is
`PriceBasis.ALL_IN_IMPORT` and is the planner input. `export_price` remains
`None`; no export compensation is inferred.

Upstream setup remains a later user action: install/configure the integration in
HA, enter the existing Zonneplan account email, and complete the verification
mail flow. HA-8C and the live RPi still report `ZONNEPLAN_LIVE = NOT_CONFIGURED`.
Nothing was installed or configured automatically.

## Corrected meter interpretation and communication follow-up

The HA-8C values are not intrinsically inconsistent:

- H122=`0` means the export-limit function/method is disabled.
- H180=`1` remains compatible with a linked/detected external meter.
- H533=`1` selects `Meter` as the anti-backflow equipment.

Thus the live evidence is compatible with a connected CHINT DDSU666 that is
not currently being used by the export-limit function. H122 was not changed.

The live broker container was inspected read-only. Its actual running command
contains:

```text
--inverter /dev/inverter --baud 115200 --bytes 8N1
```

The broker is attached to the inverter's USB/ShineWiFi connector. This
connector uses a USB serial converter and the observed link is fixed at
`115200, 8N1`; it is not the configurable physical RS485 bus used for the
BMS or external meter. H22 is live `1`, which V1.24 decodes as generic
inverter communication `38400 bps`. That value must therefore not be used to
reinterpret the fixed USB link, and the two values are not evidence of a
fault. No serial setting or H22 value was changed.

The separate BMS and DDSU666 RS485 buses remain distinct transport scopes.
Their baud/framing cannot be inferred from the USB/ShineWiFi broker command or
from generic inverter H22. The actual DDSU666 communication parameters remain
reserved for passive receive-only observation.

The DDSU666 slave address, baud, framing, polled ranges, and cadence remain a
later passive-sniff task. The topology remains inverter sole master, DDSU666
slave, and RPi receive-only observer.

## Configuration assumptions

`PlannerConfig` makes assumptions explicit and serializable. The checked-in
example uses:

| Setting | Value | Meaning |
| --- | ---: | --- |
| timezone | Europe/Amsterdam | local quarter-hour/DST context |
| usable capacity | 10 kWh | explicit ARK-class estimate, not measured |
| reserve SOC | 10% | planning floor |
| normal upper SOC | 70% | self-consumption reference |
| cheap-charge upper SOC | 80% | economic target |
| AC charge power | 3000 W | conservative planning assumption |
| charge efficiency | 92% | explicit estimate, not a measurement |
| grid limit | 35 A | installation context |
| safety margin | 3 A | planning context only |
| Growatt slots | 9 | hard representability limit |

No manufacturer flash-write endurance value is encoded.

## Planner and failsafe behavior

Supported shadow modes are `SELF_CONSUMPTION`, `CHEAP_CHARGE`, and
`FAILSAFE`. `PROFIT_EXPORT` is represented but never actionable while export
price is unavailable.

For valid telemetry and prices, battery energy is calculated as:

```text
battery-side kWh = usable_capacity * (target_soc - current_soc) / 100
grid-side kWh    = battery-side kWh / charging_efficiency
duration         = grid-side kWh / configured_AC_charge_power
```

`CHEAP_CHARGE` ranks future native quarter-hour intervals by all-in import
price, selects enough capacity for the target, preserves chronology, and
groups contiguous intervals. An optional maximum import price is respected
unless crossing it is required to reach the explicit target. The planner never
averages prices into hourly values.

The exact target gap above is continuous energy; the chosen Growatt windows
cover whole quarter-hour intervals. Cost and wear estimates therefore assume
the configured maximum AC charge power for every interval in the candidate
windows, and can model more stored energy than the target gap. The DEV view
shows that modeled margin separately. Actual charge power and final SOC can
differ; neither has been validated as a measured device response. Conversion
loss is grid energy minus stored energy, while the provisional wear cost is
applied per modeled stored kWh.

The planner returns `FAILSAFE` for stale/invalid Growatt telemetry or SOC,
invalid/stale/malformed/overlapping/gapped price data, insufficient forecast
horizon, timezone-invalid/naive input, or unavailable export-price semantics.
Failsafe means no economic optimization and normal self-consumption intent; it
does not mean repeated configuration writes.

An unavailable EV provider is not a planning prerequisite. Peblar/Zoe state is
not fabricated and no EV command is issued.

## Schedule compression and write-budget simulation

The economic selection is separate from the Growatt representation:

```text
selected quarter-hours -> contiguous economic windows
                       -> midnight-safe windows
                       -> <= 9 candidate Growatt windows
                       -> actual/desired raw-word diff
```

When scattered cheap intervals exceed nine windows, the compressor merges the
lowest-penalty neighboring gaps, keeps selected intervals represented, and
marks each affected candidate `approximate`. It reports the number of bridged
intervals and their estimated additional import cost. It never silently drops
selected intervals.

Windows are split at local midnight. Exact start/end inclusion, overlap
precedence, and midnight behavior of the device are not fully live-validated,
so every plan carries `boundary_semantics_unvalidated=true`. The live observed
outside-window behavior is retained as provenance:

```text
OUTSIDE_WINDOW_LOAD_FIRST = LIVE_OBSERVED
                            NOT_VENDOR_UNIVERSAL_RULE
```

The schedule diff compares all nine slots, including raw words and hypothetical
register pairs. An unchanged slot is counted as `would_skip_no_change`; a
changed slot is only a shadow budget item. H3036, H3037, H3047, H3048, H3049,
and H3082 are not minute-by-minute planner actuators.

## Deterministic HA-8C shadow result

The command is:

```bash
python -m ems_contract.shadow_runner \
  --inventory docs/HA-8C_LIVE_INPUT_INVENTORY.json \
  --prices tests/fixtures/ha8d_zonneplan_quarter_hour.json \
  --config tests/fixtures/ha8d_planner_config.json \
  --summary
```

Using the HA-8C live inventory and the sanitized quarter-hour fixture:

| Output | Result |
| --- | --- |
| current SOC | 10% |
| target SOC | 80% |
| required battery-side energy | 7.0 kWh |
| estimated grid-side energy | 7.6086956522 kWh |
| estimated duration | 2.5362318841 h |
| selected intervals | 11 quarter-hours, 19:00–21:45 local |
| candidate Growatt windows | one Battery First window, 19:00–21:45 |
| actual priority | Load First, I3144 raw 0 |
| actual schedule | slot 1 disabled 23:00–23:59; slot 2 enabled Battery First 00:00–07:00; slot 3 disabled 00:00–04:59 |
| hypothetical changed slots | 1–3 |
| hypothetical writes | 3 slot changes; no physical writes |
| skipped no-op slots | 6 |
| boundary flag | true |
| export optimization | false, `EXPORT_PRICE_UNAVAILABLE` |

The full structured output is reproducible with the command above; the small
checked-in [HA-8D_SHADOW_PLAN_EXAMPLE.json](HA-8D_SHADOW_PLAN_EXAMPLE.json) is
a compact scenario summary of that result.

## Cross-source diagnostic

`cross_source_balance()` is non-controlling and keeps P1 independent from
Growatt semantics. When timestamps are close it calculates:

```text
PV + battery_discharge + P1_import
  - battery_charge - P1_export - Growatt_load
```

It reports residual and timestamp-age mismatch, but never rejects a plan or
acts as electrical protection. The HA-8C-like sample residual is approximately
`-31.9 W` with aligned synthetic observations, which is informative only.

## Validation coverage

Deterministic tests cover adapter schema/scaling, missing/unavailable data,
malformed/gapped/expired forecasts, all-in negative prices, timezone/DST-aware
timestamps, SOC already at target, cheap contiguous selection, scattered-window
compression, midnight-safe behavior, stale telemetry/price failsafe, unknown
priority preservation, no-op schedule diffs, unavailable EV, export-price
disablement, cross-source residuals, and the HA-8C live inventory plan.

## Next step

The next safe step is user-driven Zonneplan setup followed by capture of one
sanitized live tariff entity state. That can validate provider freshness and
horizon behavior in shadow mode. Any Growatt schedule write, Peblar command, or
production deployment requires a separate explicitly armed task.
