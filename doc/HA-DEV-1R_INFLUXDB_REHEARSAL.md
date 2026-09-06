# HA-DEV-1R InfluxDB rehearsal

## Inventory

Production has the Supervisor add-on `a0d7b954_influxdb`, version 5.0.2,
started from `ghcr.io/hassio-addons/influxdb/aarch64:5.0.2`. Its data is on the
production host at:

`/mnt/data/supervisor/apps/data/a0d7b954_influxdb`

The add-on data measured approximately 2.0 GiB, including about 1.9 GiB of
Influx data and 76 MiB of WAL. Read-only inspection found databases `_internal`
and `homeassistant`, with the `autogen` retention policy, duration 0, shard
group duration 168h, replica 1, and `homeassistant` as default.

Home Assistant production has one active `influxdb:` writer in
`configuration.yaml`. No active Home Assistant `sensor: - platform: influxdb`,
Flux query, Grafana, Chronograf, or Node-RED reader was found in the inspected
configuration. Entity/device-registry remnants do not prove an active reader.

The add-on's upstream repository is archived and the InfluxDB 1.x line is a
maintenance/decommission concern. This should be treated separately from the
HA Core upgrade decision.

## Rehearsal treatment

* The normal Supervisor backup includes the Influx add-on and its data.
* The production YAML is preserved unchanged in the clone quarantine.
* The DEV overlay has no `influxdb:` writer.
* No InfluxDB add-on or external Influx service was started for DEV.
* HA 2026.9.0 booted and Recorder operated without the Influx writer.

## Recommendation

Disposition: `REMOVE_LEGACY_INFLUXDB`, subject to one final owner check for
external consumers not represented in Home Assistant configuration. Retain an
export/backup before removal. If a real historical-data reader is discovered,
plan that migration independently; do not keep the deprecated writer as an
implicit prerequisite for the HA Core/Growatt upgrade.
