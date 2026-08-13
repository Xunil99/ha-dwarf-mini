# tests/test_binary_sensor.py
import pytest


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
