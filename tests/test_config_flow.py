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
async def test_user_flow_succeeds_when_master_lock_claim_is_slow(
    hass, fake_dwarf_server, monkeypatch
):
    """Regression test: the connectivity probe must report success - not
    cannot_connect - when the underlying websocket connects fine but the
    best-effort master-lock claim is still pending when CONNECT_TIMEOUT
    fires (e.g. another client currently holds the lock and the device is
    slow to respond).

    Previously the claim's own 15s send_request() timeout exceeding
    CONNECT_TIMEOUT (10s) meant the outer `asyncio.wait_for(client.connect(),
    timeout=CONNECT_TIMEOUT)` cancelled connect() while it was still awaiting
    the claim - `self._ws`/`self._reader_task` were already set by then, so
    the websocket really was connected, but the cancellation escaped as
    asyncio.TimeoutError and got reported to the user as "cannot_connect"
    (a false negative), and the now-orphaned client (the config flow only
    calls client.close() on its *success* path) leaked an open websocket and
    background reader task.
    """
    from custom_components.dwarf_mini.const import CMD_SYSTEM_SET_MASTERLOCK, MODULE_SYSTEM

    # No handler registered for the master-lock claim -> the fake server
    # never answers it, so the claim blocks for its own 15s send_request
    # timeout - long enough that the shortened CONNECT_TIMEOUT below always
    # fires first, exercising the exact race this test guards against.
    del fake_dwarf_server.app["handlers"][(MODULE_SYSTEM, CMD_SYSTEM_SET_MASTERLOCK)]

    url = fake_dwarf_server.make_url("/")
    monkeypatch.setattr(
        "custom_components.dwarf_mini.config_flow.CONNECT_TIMEOUT", 0.3
    )
    monkeypatch.setattr(
        "custom_components.dwarf_mini.config_flow.DEFAULT_PORT", url.port
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    # Outer bound generous relative to the 0.3s CONNECT_TIMEOUT set above.
    result = await asyncio.wait_for(
        hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": url.host}
        ),
        timeout=2,
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == url.host

    # Entry creation auto-triggers async_setup_entry, which starts a *new*
    # long-lived client's run_forever() against fake_dwarf_server. Without
    # unloading it here, that background task (and the connection it holds
    # open) outlives the test - confirmed empirically to turn the hass
    # fixture's teardown into a ~121s hang while it works through
    # run_forever()'s reconnect-backoff chain, exactly as documented on the
    # conftest.py `connected_client` fixture this mirrors.
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_user_flow_closes_client_on_connect_failure(
    hass, mock_dwarf_connect_fails, monkeypatch
):
    """Regression test: a failed connectivity probe must always close() the
    client it created, even though today's known failure paths never leave
    anything open to close - defense in depth against a future connect()
    change reintroducing a leak on the error branch (see
    test_user_flow_succeeds_when_master_lock_claim_is_slow for the leak this
    guards against actually manifesting)."""
    from custom_components.dwarf_mini.client import DwarfMiniClient

    close_calls = []
    original_close = DwarfMiniClient.close

    async def _tracking_close(self):
        close_calls.append(self)
        await original_close(self)

    monkeypatch.setattr(DwarfMiniClient, "close", _tracking_close)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.2.50"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert len(close_calls) == 1


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
