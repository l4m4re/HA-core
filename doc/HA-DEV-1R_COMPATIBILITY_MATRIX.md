# HA-DEV-1R compatibility matrix

## Rehearsal matrix

| Test | Result | Evidence |
| --- | --- | --- |
| First boot with all copied config entries quarantined | PASS | HA 2026.9.0 initialized; frontend served on port 8123; fresh DEV onboarding completed |
| Production auth isolation | PASS | copied auth files preserved in `.ha-dev-quarantine`; DEV-only admin created in mode-600 file outside Git |
| Recorder clone/open | PASS WITH MIGRATION | copied consistent snapshot opened; schema 50 migrated to 53 |
| Influx writer isolation | PASS | DEV overlay contains no `influxdb:` writer and no Influx add-on was started |
| Frontend and DEV identity | PASS | onboarding completed; `/` returned HTTP 200; instance name is `HA DEV CLONE` |
| Energy configuration/storage load | PASS | Energy configuration and production entity registry loaded from the copy; disabled sources are intentionally unavailable during quarantine |
| HACS/custom-component reproduction | PASS WITH SCOPE | HACS 2.0.5 metadata and exact installed custom components were copied; HACS and non-Growatt entries stayed disabled for the safety baseline |
| Shelly/P1/other live integrations | QUARANTINED | copied config was retained, but live device services were not started |
| ESPHome | NOT CONFIGURED | no production ESPHome entry was found |
| Exact production Growatt component on HA 2026.9.0 | PASS WITH FOLLOW-UP | entry loaded and returned live read-only telemetry through broker 5021 |
| HA-8D development Growatt component on HA 2026.9.0 | PASS WITH FOLLOW-UP | entry loaded; existing identities retained; two new HA-8D entities registered |
| Growatt writes | NOT PERFORMED | config had `inverter_power_control: false`; no control service or write test was used |
| Peblar/Zoe controls | NOT PERFORMED | all non-Growatt entries disabled in the rehearsal |

## Growatt comparison

| Observation | Production component clone | HA-8D candidate |
| --- | --- | --- |
| HA Core | 2026.9.0 | 2026.9.0 |
| Growatt source | exact production source, manifest 0.1 | workspace source, commit `b72ddef`, manifest 0.2.1 |
| Endpoint | `192.168.1.148:5021`, unit 1 | same |
| Config entry | loaded | loaded |
| State count | 223 | 225 |
| Existing Energy entity IDs/unique IDs | retained | retained |
| Representative values | SOC 9%; PV1 7870.0 kWh; battery charge 3357.7 kWh; discharge 3220.2 kWh; energy-to-user 5.5 kWh | SOC 9%; PV1 7870.1 kWh; PV2 11705.7 kWh; battery charge 3357.7 kWh; discharge 3220.2 kWh; energy-to-user 5.5 kWh |
| New candidate entities | none | `sensor.zolder_growatt_current_priority`, `sensor.zolder_growatt_xh_schedule` |
| Transport log | FC03/FC04 reads; transaction-ID mismatch observed | FC03/FC04 reads; transaction-ID mismatch and `received pdu without a corresponding request` observed |

The transaction-ID mismatch is a pre-production follow-up, not a production
write or a failed HA startup. It is consistent with a broker/PyModbus response
ordering or buffering incompatibility and must be resolved or explicitly
accepted with evidence before a live HA Core/Growatt upgrade. The candidate
still reached `loaded` and exposed values, so the result is not a clean green
transport sign-off.

The HTTP validation errors visible in the candidate console came from the
rehearsal's own initial malformed login/API probes; they are not production
integration errors. The Modbus errors above are independent runtime evidence.

## Runtime identity and statistics conclusion

The candidate did not replace the public Energy entities. The six selected
Growatt entity IDs and unique IDs are byte-for-byte the same in the production
clone registry and candidate registry, with the same units and energy/battery
classes. The candidate added only the two HA-8D schedule/priority sensors.

This is identity continuity, not yet a cumulative-statistics migration
approval. Any future source-register change must compare old/new instantaneous
values and, for every cumulative entity, interval deltas, reset/rollover
behavior, and Recorder long-term statistics before cutover.

## Safety conclusion

The rehearsal did not transmit Growatt writes: the observed Modbus traffic was
limited to FC03 and FC04 reads, and no control path was exercised. The broker
was used as the live read-only boundary. Production remains on its original
version and configuration.

## Safety counters

* Growatt writes caused by DEV: **0**
* Peblar commands caused by DEV: **0**
* Zoe commands caused by DEV: **0**
* production HA configuration writes caused by DEV: **0**
* production Recorder/database writes caused by DEV: **0**
* production InfluxDB writes caused by DEV: **0**
