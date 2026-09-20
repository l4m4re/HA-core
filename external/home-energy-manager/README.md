# Home energy manager prototype

This directory owns the provisional, read-only EMS planner that was previously
kept in the Growatt integration repository. It is a workspace project for the
HA staging environment, not part of `growatt_local` and not an upstream
Growatt integration dependency.

The package in `ems_contract/` contains provider-neutral contracts, the
quarter-hour shadow planner, price trend calculations, and the Zoe charging
prediction model. The `custom_components/ems_shadow/` package exposes those
calculations as read-only Home Assistant staging sensors. The tests and
sanitized fixtures are kept beside the package so the move does not change
their behavior.

Run the focused suite from this directory:

```bash
cd external/home-energy-manager
PYTHONPATH=.:../Homeassistant-Growatt-Local-Modbus:../.. pytest
```

The package remains a proposal tool. It does not dispatch Growatt, Peblar, or
vehicle controls. A future standalone repository can take ownership once the
provider interfaces and data provenance are stable.
