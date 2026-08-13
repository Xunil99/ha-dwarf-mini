# tests/test_sensor.py
import asyncio

import pytest

from custom_components.dwarf_mini.proto_messages import (
    ComResWithInt,
    ResNotifyProgressCaptureRawLiveStacking,
    WsPacket,
)


@pytest.mark.asyncio
async def test_battery_sensor(hass, fake_dwarf_server, connected_client):
    """Genuine battery notification flowing through the real state machine.

    Uses the shared `connected_client` fixture (tests/conftest.py) for
    setup/cleanup. Mirrors tests/test_client.py::
    test_battery_notification_updates_state, but pushes the notification
    through a real async_setup_entry-created client/entity pair and asserts
    on hass.states.get(...) instead of reaching into client.state directly.
    """
    # Cold start: before any notification has arrived, the entity must
    # report HA's own "unknown" (native_value is None), not crash and not
    # show a stale/placeholder value.
    state = hass.states.get("sensor.dwarf_mini_battery")
    assert state is not None
    assert state.state == "unknown"

    server_ws = fake_dwarf_server.app["clients"][0]
    notify = WsPacket(
        major_version=1, minor_version=2, device_id=1,
        module_id=9, cmd=15201, type=2,
        data=ComResWithInt(value=77).SerializeToString(),
    )
    await server_ws.send_bytes(notify.SerializeToString())
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.dwarf_mini_battery")
    assert state is not None
    assert state.state == "77"
    assert state.attributes.get("unit_of_measurement") == "%"


@pytest.mark.asyncio
async def test_capture_state_sensor(hass, fake_dwarf_server, connected_client):
    """Capture-state and progress notifications through the real entity.

    Uses the shared `connected_client` fixture (tests/conftest.py) for
    setup/cleanup. Two notifications are pushed: a capture-state change
    (cmd=15208, which OPERATION_STATE_NAMES maps 1 -> "running") for the
    entity's state, and a progress update (cmd=15209) for its
    extra_state_attributes - proving both are read from the same shared
    client.state dict.
    """
    # Cold start: before any notification, native_value is None -> HA's own
    # "unknown" state (distinct from the client's "unrecognized" fallback
    # for a genuinely unmapped device value - see client.py's
    # _handle_notification).
    state = hass.states.get("sensor.dwarf_mini_capture_state")
    assert state is not None
    assert state.state == "unknown"

    server_ws = fake_dwarf_server.app["clients"][0]

    state_notify = WsPacket(
        major_version=1, minor_version=2, device_id=1,
        module_id=9, cmd=15208, type=2,
        data=ComResWithInt(value=1).SerializeToString(),
    )
    await server_ws.send_bytes(state_notify.SerializeToString())
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.dwarf_mini_capture_state")
    assert state is not None
    assert state.state == "running"

    progress_notify = WsPacket(
        major_version=1, minor_version=2, device_id=1,
        module_id=9, cmd=15209, type=2,
        data=ResNotifyProgressCaptureRawLiveStacking(
            total_count=10, current_count=3, stacked_count=2
        ).SerializeToString(),
    )
    await server_ws.send_bytes(progress_notify.SerializeToString())
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.dwarf_mini_capture_state")
    assert state is not None
    assert state.state == "running"
    assert state.attributes.get("progress_current") == 3
    assert state.attributes.get("progress_total") == 10
    assert state.attributes.get("progress_stacked") == 2
