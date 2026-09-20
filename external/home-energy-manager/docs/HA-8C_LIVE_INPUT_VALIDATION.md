# HA-8C live input validation and HIL observation baseline

Date: 2026-09-06

This is a bounded, read-only observation of the live production Home Assistant
and the development Growatt path. It does not implement tariff optimization,
issue Growatt writes, call mutating Home Assistant services, control Peblar or
Zoe, migrate entities, or deploy the development integration.

The machine-readable companion is
[HA-8C_LIVE_INPUT_INVENTORY.json](HA-8C_LIVE_INPUT_INVENTORY.json). It contains
the sanitized values and exact compatibility identities used below.

## Environment boundary

The production observer is the Home Assistant instance on `192.168.1.148`,
running HA `2025.9.3`. Its entity registry and Recorder database remain the
compatibility truth. The devcontainer is a different HA/integration version and
was used only as a HIL read client through broker `192.168.1.148:5021`, unit 1.
The broker remains the sole RTU transaction owner. No production configuration
was changed.

## Growatt feedback observation

The HA-8B typed decoder was run against the live MIN 6000TL-XH three times.
I3144 was `0` on all samples, decoding to `load_first` and remaining valid.
The actual schedule was:

| Slot | Start | End | Priority | Enabled |
| --- | --- | --- | --- | --- |
| 1 | 23:00 | 23:59 | battery_first | no |
| 2 | 00:00 | 07:00 | battery_first | yes |
| 3 | 00:00 | 04:59 | battery_first | no |
| 4–9 | 00:00 | 00:00 | load_first/raw zero | no |

The raw words are retained in the JSON inventory. The current executed mode is
therefore `load_first`, even though slot 2 is configured as an enabled
`battery_first` window; this is observation, not a schedule recommendation.

The primary evidence was the fresh temporary broker sniff stream
`/tmp/growatt-ha8c-20260906-150531.jsonl`. The existing broker analyzers were
used without creating a parser:

```text
python3 tools/analyze_sniff_log.py /tmp/growatt-ha8c-20260906-150531.jsonl \
  --client TCP:192.168.1.139:38652 --include-tcp
python3 tools/parse_live_log.py /tmp/growatt-ha8c-20260906-150531.jsonl \
  --from TCP:192.168.1.139:38652 --to TCP:192.168.1.139:38652 \
  --func 3 4 --top 20
```

The dev-client-filtered result was 6 requests and 6 responses: three complete
FC03 holding reads and three complete FC04 input reads, with zero CRC failures,
timeouts, drops, or combined-frame suspects. The bounded file also contained
simultaneous production-client traffic; that traffic was excluded from the
HIL evidence by the analyzer client filter. The raw capture is outside the
repository and is not committed.

Observed dev transaction plan:

| Function | Native page | Requests | Responses | Words returned | Result |
| --- | --- | ---: | ---: | ---: | --- |
| FC03 | H3000+125 | 3 | 3 | 125 each | repeatable |
| FC04 | I3125+125 | 3 | 3 | 125 each | repeatable |

The priority and schedule surfaces are consequently served by the existing
HA-7C pages. No one-register-per-entity transaction class was introduced. The
instrumented calls remained two vendor-native page reads per feedback snapshot.

## Production instantaneous entity inventory

Values below are live production states collected from Recorder. Instantaneous
entities have no state class in the live attributes. Ages are relative to the
collection time in the companion JSON; a zero value is not treated as fresh when
its last update is old.

| Entity | Unique ID | Unit/class | Value | Physical meaning and sign | Source |
| --- | --- | --- | ---: | --- | --- |
| `sensor.growatt_internal_wattage` | `growatt_local_SNL0CGV020_input_power` | W/power | 1087.2 | PV total, positive generation | FC04 I3001-I3002 |
| `sensor.growatt_input_1_wattage` | `growatt_local_SNL0CGV020_input_1_power` | W/power | 605.7 | PV1, positive generation | FC04 I3005-I3006 |
| `sensor.growatt_input_2_wattage` | `growatt_local_SNL0CGV020_input_2_power` | W/power | 481.5 | PV2, positive generation | FC04 I3009-I3010 |
| `sensor.growatt_power_user_load` | `growatt_local_SNL0CGV020_power_user_load` | W/power | 3801.1 | on-site load, positive consumption | FC04 I3045-I3046 |
| `sensor.growatt_power_to_user` | `growatt_local_SNL0CGV020_power_to_user` | W/power | 2573.9 | inverter to load, positive | FC04 I3041-I3042 |
| `sensor.growatt_power_to_grid` | `growatt_local_SNL0CGV020_power_to_grid` | W/power | 0.0 | inverter export, positive | FC04 I3043-I3044 |
| `sensor.growatt_charge_power` | `growatt_local_SNL0CGV020_charge_power` | W/power | 0.0 | battery charging, positive; stale | FC04 I3180-I3181 |
| `sensor.growatt_discharge_power` | `growatt_local_SNL0CGV020_discharge_power` | W/power | 142.0 | battery discharging, positive | FC04 I3178-I3179 |
| `sensor.growatt_soc` | `growatt_local_SNL0CGV020_soc` | %/battery | 10 | battery SOC | FC04 I3171 |
| `sensor.p1_power_consumption_actual_total` | `p1-pt` | kW/power | 2.54 | billing-point import, positive | P1 REST |
| `sensor.p1_power_returned_actual_total` | `p1-prt` | kW/power | 0.0 | billing-point export, positive | P1 REST |
| `sensor.p1_power_consumption_phase_1` | `p1-p1` | kW/power | 2.54 | phase-1 import, positive | P1 REST |
| `sensor.p1_current_phase_1` | `p1-a1` | A/current | 12.0 | meter-reported phase current | P1 REST |

The Growatt values at about 15:08:24 UTC were approximately 91 seconds old at
inventory capture; the P1 import value at 15:08:36 UTC was approximately 80
seconds old. Growatt export power was approximately 7 minutes old, SOC about 6
minutes old, and charge power was about 3 hours old despite being zero. These
are observed freshness facts for the future coordinator, not a new freshness
policy. The P1 `lastupdate` stream advances every 10 seconds in the sampled
history.

## Energy-dashboard continuity

The five frozen Growatt cumulative entities remain unchanged in identity,
unique-ID basis, quantity, unit, `energy` device class, and
`total_increasing` state class. The live Recorder `statistics_meta` contains
all five with source `recorder`, unit `kWh`, and sum statistics:

| Entity | Current value | Physical source |
| --- | ---: | --- |
| `sensor.growatt_input_1_total_energy` | 7867.9 kWh | FC04 I3057-I3058 |
| `sensor.growatt_input_2_total_energy` | 11705.0 kWh | FC04 I3061-I3062 |
| `sensor.growatt_battery_discharged_total` | 3220.0 kWh | FC04 I3127-I3128 |
| `sensor.growatt_battery_charged_total` | 3357.6 kWh | FC04 I3131-I3132 |
| `sensor.growatt_energy_to_user_today` | 2.1 kWh | FC04 I3067-I3068 |

No source migration was performed, so there is no old/new interval-delta
comparison to invent and no artificial counter jump. Long-term statistics were
not rewritten. Any future source change must repeat the stronger delta,
rollover/reset, and statistics-continuity validation before cutover.

## P1, provider, and cross-source observations

The existing P1 REST entities are treated as the billing/grid-point reference;
their physical backing device was not assumed to be the Growatt DDSU666. Import
and returned-energy channels are separate positive quantities. No signed-net
entity or P1 voltage entity is exposed in the live registry. The P1 `lastupdate`
entity and 10-second state history are the current freshness evidence.

At the nearby observation times, P1 import was 2.54 kW and returned power was
zero. Growatt PV was 1.087 kW, discharge was 0.142 kW, and load was 3.801 kW.
The rough balance `1.087 + 0.142 + 2.54 = 3.769 kW` is directionally
consistent within timestamp and measurement differences, but is not proof that
the two devices share a source or update instant. Growatt `power_to_user` has a
different boundary and must not be substituted for the P1 billing point.

Provider status is explicit:

- Zonneplan: `NOT_CONFIGURED`; no config entry or entity was found.
- Price provider: `NOT_CONFIGURED`.
- Peblar: `NOT_CONFIGURED`.
- Zoe: only Shelly energy/power entities are present; vehicle SOC is
  `UNAVAILABLE`.

The future SmartStuff P1 Dongle Pro should be a second read-only P1 reader whose
values are compared to the existing billing-point surface before any provider
choice. The future external-meter observation should be a passive RS485
receiver, not a second Modbus master.

## Live CHINT DDSU666 configuration evidence

The installed external meter is now identified as a CHINT DDSU666 single-phase
5(80) A RS485/Modbus-RTU meter. Growatt documentation confirms support for it
with the MIN 2500-6000TL-XH family. The live configuration read was still
read-only and did not assume the documented likely address or baud.

| Register | Live raw | Decoded meaning | Classification |
| --- | ---: | --- | --- |
| H122 | 0 | export-limit method disabled; vendor map says 1=RS485 meter, 2=RS232 meter, 3=CT | `PROVEN_EXTERNAL_METER_SETTING` |
| H180 | 1 | `MeterLink` / external meter link-detected according to normalized reference | `PROVEN_EXTERNAL_METER_SETTING` |
| H533 | 1 | anti-backflow equipment `Meter` (vendor: 1 meter, 3 CT) | `PROVEN_EXTERNAL_METER_SETTING` |
| H22 | 1 | generic inverter Modbus baud `38400` | `NOT_METER_SETTING` |
| H30 | 1 | generic inverter Modbus address `1` | `NOT_METER_SETTING` |
| H3085 | 0 | BDC/battery communication-address region; not interpreted | `NOT_METER_SETTING` |
| H3086 | 0 | BDC/battery communication-baud region; not interpreted | `NOT_METER_SETTING` |

H122, H3085, and H3086 came from accepted native-page reads. H180 and H533
returned successfully from bounded direct read-only FC03 probes; those two
single probes were not treated as repeatability proof. The H122=`disabled`
versus H180/H533 meter indications are retained as an unresolved configuration
inconsistency; nothing was changed to reconcile it.

No live register conclusively exposes the DDSU666 slave address, serial baud or
framing, a dedicated DDSU666 type code, or a meter payload health word. In
particular, the generic H22/H30 values and BDC H3085/H3086 are not used for
those meanings. No meter address or baud is therefore claimed as proven.

The Growatt quantities most suitable for later comparison with passive DDSU666
values and P1 are `I3043-I3044` grid export, `I3045-I3046` on-site load,
`I3041-I3042` inverter-to-user, and the PV/battery inputs. The passive validation
plan is:

```text
Growatt inverter (sole master) -> CHINT DDSU666 (slave)
RPi USB-RS485                -> receive-only observer
```

The observer must establish actual serial baud/framing, DDSU666 slave address,
function codes, polled ranges, request cadence, and response payloads. It must
not transmit, become a second master, or perform meter/inverter writes.

## Future HIL actuator boundary

HA-8C implements no actuator. A future bounded write test requires an explicit
exclusive HIL lease, confirmation that no production poller owns the test
window, one documented write, readback, broker sniff evidence, and immediate
release/reconciliation. Growatt schedule and persistent settings remain
`PERSISTENT_OR_UNKNOWN`; Peblar current limiting remains a future
`FAST_RUNTIME` provider and has no live control validation here.

The new `ems_contract.live_snapshot` adapter loads the sanitized inventory into
the existing HA-8B `EmsSnapshot`, `GrowattState`, priority, schedule, and
provider types. It performs no network I/O and is a fixture/validation adapter,
not a polling planner or runtime migration.

## Disposition

### GREEN WITH FOLLOW-UP

The live read-only Growatt/P1 compatibility surfaces and native HIL block-read
path are sufficiently evidenced for shadow EMS input handling; meter address/
serial settings, provider configuration, and any actuator validation remain
explicit follow-up work.
