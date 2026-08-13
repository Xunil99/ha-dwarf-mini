# tests/test_config_flow.py
import asyncio

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dwarf_mini.const import DOMAIN


@pytest.mark.asyncio
async def test_user_flow_success(hass, mock_dwarf_connect):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.2.50"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == "192.168.2.50"


@pytest.mark.asyncio
async def test_user_flow_cannot_connect(hass, mock_dwarf_connect_fails):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.2.50"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_user_flow_connect_times_out_quickly(
    hass, mock_dwarf_connect_hangs, monkeypatch
):
    """A hung connection attempt must be bounded by the flow's own timeout,
    not aiohttp's much longer defaults (sock_connect=30s, total=300s).

    Regression test: previously `client.connect()` was awaited with no
    timeout at all, so a mistyped IP / firewall dropping SYNs / powered-off
    device would leave the config form hanging for up to 30s.
    """
    monkeypatch.setattr(
        "custom_components.dwarf_mini.config_flow.CONNECT_TIMEOUT", 0.05
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    # Outer bound is generous (2s) relative to the 0.05s inner timeout we set
    # above, but far below the mock's 100s hang and aiohttp's 30s default -
    # if the flow doesn't enforce its own timeout, this wait_for fires first
    # and the test fails/errors instead of silently passing.
    result = await asyncio.wait_for(
        hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.168.2.50"}
        ),
        timeout=2,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_user_flow_unexpected_error_is_not_swallowed(
    hass, mock_dwarf_connect_broken
):
    """A real bug (e.g. AttributeError) must propagate, not be mis-reported
    to the user as cannot_connect under a catch-all `except Exception`."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with pytest.raises(AttributeError):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.168.2.50"}
        )


@pytest.mark.asyncio
async def test_user_flow_aborts_if_already_configured(hass):
    """Adding the same host twice must abort before any connection attempt.

    No mock_dwarf_connect* fixture is used here on purpose: if the abort
    check didn't run before the network call, DwarfMiniClient.connect()
    would try a real socket, which pytest-socket blocks by default -
    proving the network is never touched.
    """
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="192.168.2.50", data={"host": "192.168.2.50"}
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.2.50"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
