# tests/test_init.py
import asyncio
import logging

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dwarf_mini.const import CONF_HOST, CONF_PORT, DOMAIN


def _host_port(server):
    url = server.make_url("/")
    return url.host, url.port


@pytest.mark.asyncio
async def test_setup_and_unload_entry(hass, fake_dwarf_server, caplog):
    """End-to-end proof that async_setup_entry produces a real, connected
    DwarfMiniClient - not just hass/entry bookkeeping.

    Deliberately does NOT use the `mock_dwarf_connect` no-op patch here: that
    combo previously let run_forever() reach its `assert self._reader_task is
    not None` invariant with `_reader_task` still None (the mock never sets
    it), producing an AssertionError that run_forever()'s own broad
    `except Exception` handler swallowed and logged every single test run as
    a misleading "connection lost, retrying" warning - the test passed, but
    never actually proved a live connection was established or maintained.
    Using the real `fake_dwarf_server` fixture instead gives genuine
    end-to-end coverage of connect via async_setup_entry and a clean log.
    """
    host, port = _host_port(fake_dwarf_server)
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: host, CONF_PORT: port})
    entry.add_to_hass(hass)

    with caplog.at_level(logging.WARNING):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Storage pattern: entry.runtime_data (not hass.data[DOMAIN][entry_id]).
        client = entry.runtime_data
        assert client is not None

        for _ in range(100):
            if client.connected:
                break
            await asyncio.sleep(0.01)
        assert client.connected is True, "async_setup_entry did not establish a real connection"

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert client.connected is False

    # HA deletes the runtime_data attribute automatically once
    # async_unload_entry returns True (see ConfigEntry.async_unload).
    assert not hasattr(entry, "runtime_data")

    assert "connection lost" not in caplog.text
