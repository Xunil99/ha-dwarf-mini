# tests/test_binary_sensor.py
import asyncio

import pytest

from custom_components.dwarf_mini.const import (
    CMD_NOTIFY_STATE_ASTRO_ONE_CLICK_GOTO,
    MODULE_NOTIFY,
    STATE_RUNNING,
    STATE_STOPPED,
)
from custom_components.dwarf_mini.proto_messages import (
    OneClickGotoPhaseState,
    ResNotifyOneClickGotoState,
    WsPacket,
)


@pytest.mark.asyncio
async def test_connected_binary_sensor(hass, connected_client):
    """Genuine connect/disconnect through the real platform entity.

    Uses the shared `connected_client` fixture (tests/conftest.py) for setup:
    it builds the MockConfigEntry with the fake server's actual host/port and
    runs the real async_setup_entry, so the connect this test observes via
    run_forever() is the real one under test, and the binary_sensor entity
    picks up connectivity changes through its real add_listener callback,
    not a mocked shortcut.
    """
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.dwarf_mini_connected")
    assert state is not None
    assert state.state == "on"

    await connected_client.close()
    # run_forever() is a background task (entry.async_create_background_task),
    # so it's deliberately excluded from the plain async_block_till_done() -
    # wait_background_tasks=True is needed to let it actually process the
    # close()-triggered reader-task completion and call _notify_listeners()
    # (which is what flips the entity's state) before we assert on it.
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get("binary_sensor.dwarf_mini_connected")
    assert state.state == "off"


@pytest.mark.asyncio
async def test_tracking_binary_sensor(hass, fake_dwarf_server, connected_client):
    """Tracking notification through the real entity.

    Unlike sensor.py's "unknown" cold-start convention (native_value is
    None until the first notification arrives), client.state["tracking"]
    defaults to False (see client.py), not None - so is_on returns False,
    and the binary_sensor's own cold-start state is HA's "off", never
    "unknown". BinarySensorEntity has no not-yet-known state unless is_on
    itself returns None.
    """
    state = hass.states.get("binary_sensor.dwarf_mini_tracking")
    assert state is not None
    assert state.state == "off"

    server_ws = fake_dwarf_server.app["clients"][0]

    running_notify = WsPacket(
        major_version=1, minor_version=2, device_id=1,
        module_id=MODULE_NOTIFY, cmd=CMD_NOTIFY_STATE_ASTRO_ONE_CLICK_GOTO, type=2,
        data=ResNotifyOneClickGotoState(
            tracking_state=OneClickGotoPhaseState(state=STATE_RUNNING),
        ).SerializeToString(),
    )
    await server_ws.send_bytes(running_notify.SerializeToString())
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.dwarf_mini_tracking")
    assert state is not None
    assert state.state == "on"

    stopped_notify = WsPacket(
        major_version=1, minor_version=2, device_id=1,
        module_id=MODULE_NOTIFY, cmd=CMD_NOTIFY_STATE_ASTRO_ONE_CLICK_GOTO, type=2,
        data=ResNotifyOneClickGotoState(
            tracking_state=OneClickGotoPhaseState(state=STATE_STOPPED),
        ).SerializeToString(),
    )
    await server_ws.send_bytes(stopped_notify.SerializeToString())
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.dwarf_mini_tracking")
    assert state is not None
    assert state.state == "off"
