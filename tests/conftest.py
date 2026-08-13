# tests/conftest.py
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dwarf_mini.const import CONF_HOST, CONF_PORT, DOMAIN

# pytest-homeassistant-custom-component (registered as a pytest plugin via
# its entry point) restricts component loading to core components by
# default; its enable_custom_integrations fixture lifts that restriction so
# tests can load our custom_components/dwarf_mini package. Wrapped here as
# autouse since every test in this suite needs it and none rely on the
# restricted behavior.
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make the plugin's enable_custom_integrations fixture apply to all tests."""
    yield


@pytest.fixture
def mock_config_entry():
    return MockConfigEntry(domain=DOMAIN, data={"host": "192.168.2.50", "port": 9900})


class _FakeWs:
    """Minimal aiohttp.ClientWebSocketResponse stand-in for mock_dwarf_connect."""

    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


async def _fake_reader_loop() -> None:
    """Stand-in for DwarfMiniClient._reader_loop(): blocks until cancelled.

    Mirrors the real reader loop's own CancelledError handling (swallow, end
    cleanly) so a caller doing `self._reader_task.cancel(); await
    self._reader_task` (close()) or `await self._reader_task` (run_forever())
    sees the same "completes with no exception" behavior the real loop
    produces on a deliberate close(), rather than an unhandled CancelledError.
    """
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass


async def _fake_connect(self) -> None:
    """side_effect for mock_dwarf_connect: a faithful (not just no-op) fake.

    Sets `_ws`/`_reader_task` the way the real connect() does, rather than
    leaving them None. Without this, `run_forever()`'s
    `assert self._reader_task is not None` (evaluated right after connect())
    fails - but that AssertionError is an Exception, so run_forever()'s own
    broad `except Exception` swallows it and logs a misleading "connection
    lost, retrying" warning instead of surfacing a real failure. This isn't
    just theoretical: it's silently triggered by any test that reaches a
    *real* async_setup_entry with this mock active - e.g. a config flow's
    async_create_entry auto-triggers entry setup, which starts run_forever()
    as a background task against a freshly constructed client whose
    (mocked) connect() would otherwise leave _reader_task unset.
    Uses autospec=True (see the patch() call below) so `self` is passed in
    like a real bound method call - a plain AsyncMock replacing a class
    method does not bind `self` automatically.
    """
    self._closing_event.clear()
    if self.connected:
        return
    self._ws = _FakeWs()
    self._reader_task = asyncio.create_task(_fake_reader_loop())


@pytest.fixture
def mock_dwarf_connect():
    """Patch DwarfMiniClient.connect to succeed with a realistic fake state.

    See _fake_connect()'s docstring for why this can't be a plain no-op.
    """
    with patch(
        "custom_components.dwarf_mini.client.DwarfMiniClient.connect",
        autospec=True,
        side_effect=_fake_connect,
    ) as mock_connect:
        yield mock_connect


@pytest.fixture
def mock_dwarf_connect_fails():
    """Patch DwarfMiniClient.connect to raise, simulating an unreachable device."""
    with patch(
        "custom_components.dwarf_mini.client.DwarfMiniClient.connect",
        new_callable=AsyncMock,
        side_effect=ConnectionError("cannot connect"),
    ) as mock_connect:
        yield mock_connect


@pytest.fixture
def mock_dwarf_connect_hangs():
    """Patch DwarfMiniClient.connect to hang indefinitely.

    Simulates a mistyped IP, a firewall silently dropping SYNs, or a
    powered-off-but-still-routed device: the TCP handshake never resolves on
    its own. Used to prove the config flow enforces its own timeout instead
    of relying on aiohttp's much longer defaults.
    """

    async def _hang(*_args, **_kwargs):
        await asyncio.sleep(100)

    with patch(
        "custom_components.dwarf_mini.client.DwarfMiniClient.connect",
        new_callable=AsyncMock,
        side_effect=_hang,
    ) as mock_connect:
        yield mock_connect


@pytest.fixture
def mock_dwarf_connect_broken():
    """Patch DwarfMiniClient.connect to raise an unexpected programming error.

    Distinct from mock_dwarf_connect_fails (a plausible network failure):
    this simulates a real bug (e.g. an AttributeError from a client-code
    defect) that must not be silently mis-reported to the user as
    "cannot_connect".
    """
    with patch(
        "custom_components.dwarf_mini.client.DwarfMiniClient.connect",
        new_callable=AsyncMock,
        side_effect=AttributeError("boom"),
    ) as mock_connect:
        yield mock_connect


@pytest.fixture
async def fake_dwarf_server(aiohttp_client, socket_enabled):
    """Minimal WS server that echoes framed requests back as their response.

    Handlers are registered per test via `app["handlers"][(module_id, cmd)] = fn`,
    where fn(data: bytes) -> bytes returns the serialized response payload.

    Depends on pytest-homeassistant-custom-component's `socket_enabled` fixture:
    that plugin disables real socket.socket() creation by default for every
    test (a Home Assistant core testing safety net), which would otherwise
    break aiohttp_client's real TCP test server used here.
    """
    app = web.Application()
    app["handlers"] = {}
    app["clients"] = []

    async def ws_handler(request):
        from custom_components.dwarf_mini.proto_messages import WsPacket

        ws = web.WebSocketResponse()
        await ws.prepare(request)
        app["clients"].append(ws)
        async for msg in ws:
            if msg.type != web.WSMsgType.BINARY:
                continue
            packet = WsPacket()
            packet.ParseFromString(msg.data)
            handler = app["handlers"].get((packet.module_id, packet.cmd))
            if handler is None:
                continue
            response_data = handler(packet.data)
            response = WsPacket()
            response.major_version = 1
            response.minor_version = 2
            response.device_id = 1
            response.module_id = packet.module_id
            response.cmd = packet.cmd
            response.type = 1  # TYPE_REQUEST_RESPONSE
            response.data = response_data
            await ws.send_bytes(response.SerializeToString())
        return ws

    app.router.add_get("/", ws_handler)
    client = await aiohttp_client(app)
    yield client


@pytest.fixture
async def connected_client(hass, fake_dwarf_server):
    """A real DwarfMiniClient, connected, behind a real config entry.

    Shared by test_binary_sensor.py, test_sensor.py and test_button.py:
    builds a MockConfigEntry pointed at fake_dwarf_server's actual host/port,
    runs the real async_setup_entry (so the platform entities under test are
    wired up exactly as they are in production), and waits for the client's real
    connect() - kicked off by run_forever() - to land before yielding the
    client for the test to push notifications through.

    The `finally` around the yield is not optional: without it, a test that
    fails/asserts before reaching its own cleanup leaves the entry's
    run_forever() background task alive, still holding the fake_dwarf_server
    connection open. That task then has to run through its full
    reconnect-backoff chain during the hass fixture's own teardown before the
    test session can proceed - confirmed empirically to take up to ~121s per
    stuck test, turning one assertion failure into a near-total suite hang.
    Closing here unconditionally keeps that guarantee in one place instead of
    requiring every test that uses this fixture to remember its own
    try/finally.
    """
    url = fake_dwarf_server.make_url("/")
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: url.host, CONF_PORT: url.port}
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    dwarf_client = entry.runtime_data
    for _ in range(100):
        if dwarf_client.connected:
            break
        await asyncio.sleep(0.01)
    assert dwarf_client.connected is True

    try:
        yield dwarf_client
    finally:
        # Idempotent even if the test already called close() itself (e.g.
        # test_binary_sensor.py's disconnect assertion) - DwarfMiniClient.close()
        # no-ops cleanly on an already-closed client.
        await dwarf_client.close()
