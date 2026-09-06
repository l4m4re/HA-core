# HA-DEV-1R production inventory

Date: 2026-09-06

This is a read-only inventory of the Home Assistant installation on
`192.168.1.148`, prepared for the disposable HA-DEV-1R upgrade rehearsal. It
does not authorize or describe a production migration.

## Platform

| Item | Production |
| --- | --- |
| Home Assistant OS | 16.1, `rpi4-64`, aarch64 |
| Home Assistant Core | 2025.9.3 |
| Supervisor | 2026.08.0, healthy, reported unsupported |
| HA Core rehearsal | 2026.9.0 from this workspace |
| Growatt production component | manifest version 0.1 |
| Growatt development candidate | HA-8D lineage, commit `b72ddef4c5e5a85e156c54baf2cf96bee2241515`, manifest 0.2.1 |
| Growatt endpoint used in rehearsal | broker `192.168.1.148:5021`, unit 1, read-only test |

The live Growatt config entry is `Growatt MIN 6000TL-XH`, serial `SNL0CGV020`,
model `MIN 6000TL-XH`, type `hybrid_120_TL_XH`, TCP communication, address 1,
and `inverter_power_control: false`. The production endpoint remains port
5020; only the disposable clone was pointed at broker port 5021.

## Supervisor add-ons

| Add-on | Version | Observed state | HA-DEV-1R classification |
| --- | --- | --- | --- |
| File editor (`core_configurator`) | 5.8.0 | started | Supervisor convenience only |
| pigpio | 1.5.3-migrate | started | hardware-specific; not required for Core compatibility |
| InfluxDB (`a0d7b954_influxdb`) | 5.0.2 | started | legacy/decommission candidate; separate report |
| Mosquitto | 6.5.2 | started | external MQTT dependency candidate, quarantined in DEV |
| ser2net | 0.0.3 | stopped | not required for this rehearsal |
| Advanced SSH | 21.0.3 | started | administration only |
| Tailscale | 0.26.1 | started | administration/network only |
| Get HACS | 1.3.1 | stopped | installer only |

HACS itself is version 2.0.5. Other installed custom integrations observed
were LocalTuya 5.2.3, pyscript 1.6.4, and rpi_gpio_pwm V2024.8.0. Their files
were preserved in the clone but their config entries were disabled during the
quarantine boot.

Zonneplan was not installed or configured in the production inventory. It is
therefore a later, new DEV integration and is not part of the baseline verdict.

## Production backup and Recorder snapshot

A normal Supervisor full backup was created before cloning:

* slug `5852fb45`
* name `HA-DEV-1R-production-20260906`
* size 1,566,412,800 bytes
* SHA-256 `faf8acba94d504af26bb70f28dfb065eb2db7634a2cfca97ac60a2a08643c1b0`

The backup includes Home Assistant, the add-ons, `share`, `ssl`, and media;
the InfluxDB add-on data is included. The archive is outside Git at
`/tmp/HA-dev-1R-20260906/5852fb45.tar`.

A separate SQLite backup made with SQLite's online backup API is outside Git
at `/tmp/HA-dev-1R-20260906/recorder.db`. It has SHA-256
`91bba8534e0eb1b6f85501d37ef0e806a447c03ece0570ab3b6d6f96e2c4f897` and passed
a read-only integrity check. The production snapshot contained:

* Recorder schema version 50;
* 1,183,856 `states` rows and 66,879 `events` rows;
* 829,810 long-term `statistics` rows and 122,088 short-term rows;
* 127 `statistics_meta` records and 3,053 statistics runs.

On the disposable HA 2026.9.0 boot Recorder migrated the copied database from
schema 50 to 53. Production was not opened by this process.

## Energy-dashboard sensor continuity baseline

The following public entities were found in the live Energy configuration and
their registry identities were preserved in the clone. The Growatt entries
were checked against the cloned entity registry; the P1 and Zoe entities were
also inventoried as external Energy sources.

| Entity | Unique ID | Device class | State class | Unit | Physical meaning/source |
| --- | --- | --- | --- | --- | --- |
| `sensor.growatt_input_1_total_energy` | `growatt_local_SNL0CGV020_input_1_energy_total` | energy | total_increasing | kWh | PV input 1 cumulative energy |
| `sensor.growatt_input_2_total_energy` | `growatt_local_SNL0CGV020_input_2_energy_total` | energy | total_increasing | kWh | PV input 2 cumulative energy |
| `sensor.growatt_battery_charged_total` | `growatt_local_SNL0CGV020_charge_energy_total` | energy | total_increasing | kWh | battery charged cumulative energy |
| `sensor.growatt_battery_discharged_total` | `growatt_local_SNL0CGV020_discharge_energy_total` | energy | total_increasing | kWh | battery discharged cumulative energy |
| `sensor.growatt_energy_to_user_today` | `growatt_local_SNL0CGV020_energy_to_user_today` | energy | total_increasing | kWh | Growatt daily energy-to-user counter |
| `sensor.growatt_soc` | `growatt_local_SNL0CGV020_soc` | battery | not applicable | % | instantaneous battery SOC |
| `sensor.p1_energy_consumption_tariff_1` | `p1-t1` | energy | total_increasing | kWh | P1 grid import tariff 1 |
| `sensor.p1_energy_consumption_tariff_2` | `p1-t2` | energy | total_increasing | kWh | P1 grid import tariff 2 |
| `sensor.p1_energy_returned_tariff_1` | `p1-rt1` | energy | total_increasing | kWh | P1 grid export tariff 1 |
| `sensor.p1_energy_returned_tariff_2` | `p1-rt2` | energy | total_increasing | kWh | P1 grid export tariff 2 |
| `sensor.zoef_energy` | `E465B8F1DDD4-switch:0-energy` | energy | total_increasing | kWh | Shelly/Zoe cumulative energy |

The source-register assignments and sign conventions are recorded as a
compatibility concern rather than silently migrated. The DEV run observed a
reconstructed `energy_to_user_today` value moving from 5.3 to 4.3 during
startup, which is a concrete warning that cumulative/day-counter continuity
needs interval-delta and reset validation before any production source change.

## Clone locations and safety boundary

The source backup, production clone, Recorder copy, credentials, and exact
production Growatt source are all outside Git under
`/tmp/HA-dev-1R-20260906/`. The production configuration is preserved inside
the clone's `.ha-dev-quarantine/` directory. No production YAML, config-entry
store, entity registry, add-on state, or database was modified.
