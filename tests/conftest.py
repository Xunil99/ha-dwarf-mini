# tests/conftest.py
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web

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
def mock_dwarf_connect():
    """Patch DwarfMiniClient.connect to succeed as a no-op."""
    with patch(
        "custom_components.dwarf_mini.client.DwarfMiniClient.connect",
        new_callable=AsyncMock,
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
