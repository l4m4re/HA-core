# ZABA22 VPP original-code fixtures

This directory contains bounded Unicorn executions of the unchanged
`external/growatt-firmware/ALBA18/ZABA22-payload.bin`. The fixtures map only
the payload's flash image and a zeroed SRAM window; they never open a serial,
Modbus, Home Assistant or production connection.

Run the executable evidence with:

```text
python3 -m pytest -q research/zaba22_original_rehosting/test_vpp_original.py
```

`execute_fc06_pending_gate` starts at the original FC06 pending check and
stops at its original response-construction branch. A clear mask is allowed
to continue into the unmodelled downstream dispatcher; that is recorded as a
blocker, not replaced by a model.

`execute_bridge` starts at original `FUN_0801474C` and stops at its natural
common-return PC `0x0801491E`. The fixture values are explicitly hypothetical
SRAM inputs, not claims about firmware-initialized or live state.
