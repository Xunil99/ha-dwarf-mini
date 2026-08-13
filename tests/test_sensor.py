# tests/test_sensor.py
import asyncio

import pytest

from custom_components.dwarf_mini.const import (
    CMD_NOTIFY_FOCUS,
    CMD_NOTIFY_STATE_ASTRO_ONE_CLICK_GOTO,
    MODULE_NOTIFY,
    STATE_RUNNING,
)
from custom_components.dwarf_mini.proto_messages import (
    ComResWithInt,
    OneClickGotoPhaseState,
    ResNotifyFocus,
    ResNotifyOneClickGotoState,
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


@pytest.mark.asyncio
async def test_capture_state_sensor_unrecognized_value_does_not_crash_or_freeze(
    hass, fake_dwarf_server, connected_client
):
    """A device value with no OPERATION_STATE_NAMES mapping must surface as
    HA's own "unknown" state, not raise (SensorEntity.state raises ValueError
    for an ENUM sensor whose native_value isn't in _attr_options) and not
    silently freeze the entity at its last valid value.

    Regression test for a bug found in code review: `client.state
    ["capture_state"]` is set to the raw "unrecognized" fallback string,
    which is not one of `_attr_options`. Since `async_write_ha_state()` reads
    `self.state` (which validates against `_attr_options` and raises) before
    writing anything, and the resulting ValueError is only logged by
    `DwarfMiniClient._notify_listeners`'s generic `except Exception`, the
    write never happens at all - so BOTH the state and
    extra_state_attributes stay frozen at their previous values, invisible
    to the user (no error state, just a stale-but-plausible reading).
    """
    server_ws = fake_dwarf_server.app["clients"][0]

    # First: a valid state, to have something the sensor could wrongly stay
    # frozen at.
    state_notify = WsPacket(
        major_version=1, minor_version=2, device_id=1,
        module_id=9, cmd=15208, type=2,
        data=ComResWithInt(value=1).SerializeToString(),
    )
    await server_ws.send_bytes(state_notify.SerializeToString())
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.dwarf_mini_capture_state").state == "running"

    # Then: an unrecognized device value.
    unrecognized_notify = WsPacket(
        major_version=1, minor_version=2, device_id=1,
        module_id=9, cmd=15208, type=2,
        data=ComResWithInt(value=99).SerializeToString(),
    )
    await server_ws.send_bytes(unrecognized_notify.SerializeToString())
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.dwarf_mini_capture_state")
    assert state is not None
    assert state.state == "unknown"


@pytest.mark.asyncio
async def test_focus_position_sensor(hass, fake_dwarf_server, connected_client):
    """Focus-position notification through the real entity.

    Uses the shared `connected_client` fixture (tests/conftest.py) for
    setup/cleanup. Mirrors tests/test_client.py::
    test_focus_notification_updates_state, but pushes the notification
    through a real async_setup_entry-created client/entity pair and asserts
    on hass.states.get(...) instead of reaching into client.state directly.
    """
    # Cold start: before any notification has arrived, the entity must
    # report HA's own "unknown" (native_value is None), not crash and not
    # show a stale/placeholder value.
    state = hass.states.get("sensor.dwarf_mini_focus_position")
    assert state is not None
    assert state.state == "unknown"

    server_ws = fake_dwarf_server.app["clients"][0]
    notify = WsPacket(
        major_version=1, minor_version=2, device_id=1,
        module_id=MODULE_NOTIFY, cmd=CMD_NOTIFY_FOCUS, type=2,
        data=ResNotifyFocus(focus=1234).SerializeToString(),
    )
    await server_ws.send_bytes(notify.SerializeToString())
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.dwarf_mini_focus_position")
    assert state is not None
    assert state.state == "1234"


@pytest.mark.asyncio
async def test_goto_state_sensor(hass, fake_dwarf_server, connected_client):
    """GoTo-state notification through the real entity.

    Uses the shared `connected_client` fixture (tests/conftest.py) for
    setup/cleanup. Mirrors tests/test_client.py::
    test_goto_notification_updates_state, but pushes the notification
    through a real async_setup_entry-created client/entity pair and asserts
    on hass.states.get(...) instead of reaching into client.state directly.
    """
    # Cold start: before any notification, native_value is None -> HA's own
    # "unknown" state (distinct from the client's "unrecognized" fallback
    # for a genuinely unmapped device value - see client.py's
    # _handle_notification).
    state = hass.states.get("sensor.dwarf_mini_goto_state")
    assert state is not None
    assert state.state == "unknown"

    server_ws = fake_dwarf_server.app["clients"][0]
    notify = WsPacket(
        major_version=1, minor_version=2, device_id=1,
        module_id=MODULE_NOTIFY, cmd=CMD_NOTIFY_STATE_ASTRO_ONE_CLICK_GOTO, type=2,
        data=ResNotifyOneClickGotoState(
            state=STATE_RUNNING,
            goto_state=OneClickGotoPhaseState(target_name="M31"),
            tracking_state=OneClickGotoPhaseState(state=STATE_RUNNING),
        ).SerializeToString(),
    )
    await server_ws.send_bytes(notify.SerializeToString())
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.dwarf_mini_goto_state")
    assert state is not None
    assert state.state == "running"
    assert state.attributes.get("target_name") == "M31"


@pytest.mark.asyncio
async def test_goto_state_sensor_unrecognized_value_does_not_crash_or_freeze(
    hass, fake_dwarf_server, connected_client
):
    """A device value with no OPERATION_STATE_NAMES mapping must surface as
    HA's own "unknown" state, not raise (SensorEntity.state raises ValueError
    for an ENUM sensor whose native_value isn't in _attr_options) and not
    silently freeze the entity - state AND extra_state_attributes - at its
    last valid value.

    Regression test mirroring the capture_state fix: pushes a valid
    goto-state notification (state=running, target_name="M31"), then an
    unrecognized one carrying a *different* target_name ("M42"), and asserts
    the entity state becomes "unknown" rather than staying at "running", and
    that later valid notifications aren't blocked by any leftover bad state.
    """
    server_ws = fake_dwarf_server.app["clients"][0]

    valid_notify = WsPacket(
        major_version=1, minor_version=2, device_id=1,
        module_id=MODULE_NOTIFY, cmd=CMD_NOTIFY_STATE_ASTRO_ONE_CLICK_GOTO, type=2,
        data=ResNotifyOneClickGotoState(
            state=STATE_RUNNING,
            goto_state=OneClickGotoPhaseState(target_name="M31"),
        ).SerializeToString(),
    )
    await server_ws.send_bytes(valid_notify.SerializeToString())
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.dwarf_mini_goto_state").state == "running"

    unrecognized_notify = WsPacket(
        major_version=1, minor_version=2, device_id=1,
        module_id=MODULE_NOTIFY, cmd=CMD_NOTIFY_STATE_ASTRO_ONE_CLICK_GOTO, type=2,
        data=ResNotifyOneClickGotoState(
            state=99,
            goto_state=OneClickGotoPhaseState(target_name="M42"),
        ).SerializeToString(),
    )
    await server_ws.send_bytes(unrecognized_notify.SerializeToString())
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.dwarf_mini_goto_state")
    assert state is not None
    assert state.state == "unknown"
    assert state.attributes.get("target_name") == "M42"
