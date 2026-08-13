# tests/test_client.py
import asyncio
import logging

import pytest

from custom_components.dwarf_mini.client import DwarfMiniClient
from custom_components.dwarf_mini.proto_messages import (
    TYPE_REQUEST_RESPONSE,
    ComResponse,
    ComResWithInt,
    ReqStopCaptureRawLiveStacking,
    WsPacket,
)


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


@pytest.mark.asyncio
async def test_battery_notification_updates_state(fake_dwarf_server):
    client = DwarfMiniClient(
        session=fake_dwarf_server.session,
        ws_url=_ws_url(fake_dwarf_server),
    )
    await client.connect()

    updates = []
    client.add_listener(lambda: updates.append(dict(client.state)))

    # Simulate the device pushing a battery notification.
    server_ws = fake_dwarf_server.app["clients"][0]
    notify = WsPacket(
        major_version=1, minor_version=2, device_id=1,
        module_id=9, cmd=15201, type=2,
        data=ComResWithInt(value=77).SerializeToString(),
    )
    await server_ws.send_bytes(notify.SerializeToString())
    await asyncio.sleep(0.05)

    assert client.state["battery_percent"] == 77
    assert updates and updates[-1]["battery_percent"] == 77
    await client.close()


@pytest.mark.asyncio
async def test_run_forever_notifies_listeners_on_disconnect_and_reconnect(fake_dwarf_server):
    """Regression test for the critical review-round-3 bug: run_forever()
    must call _notify_listeners() on connectivity changes, not just on
    state-dict changes — otherwise a push-only connectivity binary_sensor
    (Task 8) would never learn about a disconnect."""
    client = DwarfMiniClient(
        session=fake_dwarf_server.session,
        ws_url=_ws_url(fake_dwarf_server),
        reconnect_initial_delay=0.05,
        reconnect_max_delay=0.05,
    )

    events = []
    client.add_listener(lambda: events.append(client.connected))

    task = asyncio.create_task(client.run_forever())
    for _ in range(100):
        if events:
            break
        await asyncio.sleep(0.01)
    assert events == [True]

    server_ws = fake_dwarf_server.app["clients"][0]
    await server_ws.close()

    for _ in range(100):
        if len(events) >= 2:
            break
        await asyncio.sleep(0.01)
    assert events[1] is False, f"expected a disconnect notification, got {events}"

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await client.close()


@pytest.mark.asyncio
async def test_close_during_backoff_wait_ends_run_forever_promptly(fake_dwarf_server):
    """Regression test for the review-round-2 close()-during-backoff race:
    close() called while run_forever() is mid-backoff-wait must end
    run_forever() promptly, not only after the full backoff delay elapses.
    Uses a short configured delay so the test itself stays fast."""
    client = DwarfMiniClient(
        session=fake_dwarf_server.session,
        ws_url=_ws_url(fake_dwarf_server),
        reconnect_initial_delay=0.3,
        reconnect_max_delay=0.3,
    )
    await client.connect()

    async def _boom(_packet: WsPacket) -> None:
        raise RuntimeError("boom")

    client._dispatch = _boom  # type: ignore[method-assign]

    task = asyncio.create_task(client.run_forever())

    server_ws = fake_dwarf_server.app["clients"][0]
    packet = WsPacket(module_id=1, cmd=1, type=TYPE_REQUEST_RESPONSE, data=b"")
    await server_ws.send_bytes(packet.SerializeToString())

    for _ in range(100):
        if not client.connected:
            break
        await asyncio.sleep(0.01)
    assert client.connected is False

    await asyncio.sleep(0.05)  # make sure run_forever() is inside the backoff wait

    loop = asyncio.get_running_loop()
    start = loop.time()
    await client.close()
    await asyncio.wait_for(task, timeout=1.0)
    elapsed = loop.time() - start

    assert elapsed < 0.15, f"run_forever() took {elapsed:.3f}s to end after close()"


def test_notify_listeners_isolates_callback_errors():
    """Regression test for the review-round-3 important bug: one listener
    raising must not stop the remaining listeners from being notified."""
    client = DwarfMiniClient(session=object(), ws_url="ws://example.invalid")
    calls = []

    def bad() -> None:
        raise RuntimeError("listener boom")

    def good() -> None:
        calls.append("good")

    client.add_listener(bad)
    client.add_listener(good)

    client._notify_listeners()

    assert calls == ["good"]


@pytest.mark.asyncio
async def test_malformed_notification_payload_is_logged_and_swallowed(
    fake_dwarf_server, caplog
):
    """Regression test for the review-round-3 important bug: a corrupt
    notification payload must be logged and dropped, not silently swallowed
    (and must not crash the reader loop or leave stale/garbage state)."""
    client = DwarfMiniClient(
        session=fake_dwarf_server.session,
        ws_url=_ws_url(fake_dwarf_server),
    )
    await client.connect()

    server_ws = fake_dwarf_server.app["clients"][0]
    notify = WsPacket(
        major_version=1, minor_version=2, device_id=1,
        module_id=9, cmd=15201, type=2,
        data=b"\x08",  # truncated varint field -> DecodeError on parse
    )
    with caplog.at_level(logging.DEBUG, logger="custom_components.dwarf_mini.client"):
        await server_ws.send_bytes(notify.SerializeToString())
        await asyncio.sleep(0.05)

    assert client.state["battery_percent"] is None
    assert client.connected is True
    assert any(
        "failed to decode notification payload" in record.message
        for record in caplog.records
    )

    await client.close()


@pytest.mark.asyncio
async def test_send_request_gets_response(fake_dwarf_server):
    fake_dwarf_server.app["handlers"][(3, 11006)] = (
        lambda data: ComResponse(code=0).SerializeToString()
    )
    client = DwarfMiniClient(
        session=fake_dwarf_server.session,
        ws_url=_ws_url(fake_dwarf_server),
    )
    response = await client.send_request(
        3, 11006, ReqStopCaptureRawLiveStacking(), ComResponse
    )
    assert response.code == 0
    await client.close()
