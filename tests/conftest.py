# tests/conftest.py
import pytest
from aiohttp import web


@pytest.fixture
async def fake_dwarf_server(aiohttp_client):
    """Minimal WS server that echoes framed requests back as their response.

    Handlers are registered per test via `app["handlers"][(module_id, cmd)] = fn`,
    where fn(data: bytes) -> bytes returns the serialized response payload.
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
