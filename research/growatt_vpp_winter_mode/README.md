# Growatt VPP/Winter Mode study

This directory is the reviewable offline increment for the MIN TL-XH Winter
Mode/VPP investigation. `evidence.json` is the evidence index. `model.py` is a
deliberately small replay model. `REPORT.md` is generated from the evidence
index by `generate_report.py`; it is not a second source of truth.

Run:

```sh
python3 -m pytest research/growatt_vpp_winter_mode/test_model.py
python3 research/growatt_vpp_winter_mode/generate_report.py > /tmp/growatt-vpp-report.md
```

The model has no network or Modbus client and cannot affect an inverter,
battery, or production Home Assistant.
