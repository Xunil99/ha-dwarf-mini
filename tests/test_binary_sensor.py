# tests/test_binary_sensor.py
import asyncio

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dwarf_mini.const import CONF_HOST, CONF_PORT, DOMAIN


@pytest.mark.asyncio
async def test_connected_binary_sensor(hass, fake_dwarf_server):
    """Genuine connect/disconnect through the real platform entity.

    Builds the MockConfigEntry with the fake server's actual host/port (the
    same approach test_init.py uses) instead of reaching into
    client._ws_url after the fact - async_setup_entry then constructs the
    client already pointed at fake_dwarf_server, so the connect it kicks off
    via run_forever() is the real one under test, and the binary_sensor
    entity picks up connectivity changes through its real add_listener
    callback, not a mocked shortcut.
    """
    url = fake_dwarf_server.make_url("/")
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: url.host, CONF_PORT: url.port}
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    client = entry.runtime_data

    for _ in range(100):
        if client.connected:
            break
        await asyncio.sleep(0.01)
    assert client.connected is True

    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.dwarf_mini_connected")
    assert state is not None
    assert state.state == "on"

    await client.close()
    # run_forever() is a background task (entry.async_create_background_task),
    # so it's deliberately excluded from the plain async_block_till_done() -
    # wait_background_tasks=True is needed to let it actually process the
    # close()-triggered reader-task completion and call _notify_listeners()
    # (which is what flips the entity's state) before we assert on it.
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get("binary_sensor.dwarf_mini_connected")
    assert state.state == "off"
