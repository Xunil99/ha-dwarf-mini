# tests/test_client.py
import asyncio

import pytest

from custom_components.dwarf_mini.client import DwarfMiniClient
from custom_components.dwarf_mini.proto_messages import TYPE_REQUEST_RESPONSE, WsPacket


def _ws_url(server) -> str:
    return str(server.make_url("/")).replace("http://", "ws://")


@pytest.mark.asyncio
async def test_connect_and_close(fake_dwarf_server):
    client = DwarfMiniClient(
        session=fake_dwarf_server.session,
        ws_url=_ws_url(fake_dwarf_server),
    )
    await client.connect()
    assert client.connected is True
    await client.close()
    assert client.connected is False


@pytest.mark.asyncio
async def test_reader_loop_exception_invalidates_connection(fake_dwarf_server):
    """Regression test for critical bug #1: a reader-loop exception (e.g. a
    DecodeError while parsing a response) must invalidate the connection
    immediately, and close() must not re-raise it afterwards."""
    client = DwarfMiniClient(
        session=fake_dwarf_server.session,
        ws_url=_ws_url(fake_dwarf_server),
    )
    await client.connect()
    assert client.connected is True

    async def _boom(_packet: WsPacket) -> None:
        raise RuntimeError("boom")

    # Force the reader loop to die on its next dispatched message.
    client._dispatch = _boom  # type: ignore[method-assign]

    server_ws = fake_dwarf_server.app["clients"][0]
    packet = WsPacket(module_id=1, cmd=1, type=TYPE_REQUEST_RESPONSE, data=b"")
    await server_ws.send_bytes(packet.SerializeToString())

    # Give the reader task a chance to process the message and die.
    for _ in range(100):
        if not client.connected:
            break
        await asyncio.sleep(0.01)

    assert client.connected is False

    # close() must clean up quietly, not re-raise the reader task's RuntimeError.
    await client.close()
    assert client.connected is False


@pytest.mark.asyncio
async def test_send_request_fails_fast_on_clean_disconnect(fake_dwarf_server):
    """Regression test for important bug #3: a clean server-side disconnect
    must fail an in-flight send_request() promptly, not only after the full
    timeout elapses."""
    client = DwarfMiniClient(
        session=fake_dwarf_server.session,
        ws_url=_ws_url(fake_dwarf_server),
    )
    await client.connect()

    async def _close_server_side_soon() -> None:
        await asyncio.sleep(0.05)
        server_ws = fake_dwarf_server.app["clients"][0]
        await server_ws.close()

    asyncio.create_task(_close_server_side_soon())

    loop = asyncio.get_running_loop()
    start = loop.time()
    with pytest.raises(ConnectionError):
        # No handler is registered for module 99/cmd 99, so the fake server
        # never answers this on its own — only the disconnect should end it.
        await client.send_request(
            module_id=99,
            cmd=99,
            request_message=WsPacket(),
            response_cls=WsPacket,
            timeout=5.0,
        )
    elapsed = loop.time() - start

    assert elapsed < 1.0, f"send_request took {elapsed:.2f}s, should fail fast on disconnect"
