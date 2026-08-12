# custom_components/dwarf_mini/client.py
"""WebSocket client for the DWARF mini V3 control protocol.

Connection handling, envelope framing and request/response correlation are ported
from dwarfAlp's src/dwarf_alpaca/dwarf/ws_client.py (DwarfWsClient class,
https://github.com/acocalypso/dwarfAlp, GPLv3), adapted to use aiohttp (already a
Home Assistant core dependency) instead of the `websockets` package.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

import aiohttp
from google.protobuf.message import DecodeError, Message

from .proto_messages import (
    TYPE_NOTIFICATION,
    TYPE_REQUEST,
    TYPE_REQUEST_RESPONSE,
    WsPacket,
)

_LOGGER = logging.getLogger(__name__)

NotificationHandler = Callable[[WsPacket], Coroutine[Any, Any, None]]


@dataclass
class _PendingRequest:
    future: "asyncio.Future[Message]"
    response_cls: type[Message]


class DwarfMiniClient:
    """Lightweight websocket client for the DWARF mini control plane."""

    def __init__(
        self,
        *,
        session: aiohttp.ClientSession,
        ws_url: str,
        client_id: str = "ha-dwarf-mini",
    ) -> None:
        self._session = session
        self._ws_url = ws_url
        self._client_id = client_id

        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._pending: dict[tuple[int, int], _PendingRequest] = {}
        self._notification_handlers: set[NotificationHandler] = set()
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    async def connect(self) -> None:
        if self.connected:
            return
        async with self._lock:
            if self.connected:
                return
            self._ws = await self._session.ws_connect(self._ws_url, heartbeat=None)
            self._reader_task = asyncio.create_task(self._reader_loop())
            self._reader_task.add_done_callback(self._on_reader_task_done)

    async def close(self) -> None:
        async with self._lock:
            if self._reader_task:
                self._reader_task.cancel()
                # The reader task may end with CancelledError (the common case,
                # triggered by the cancel() above) or with whatever exception
                # killed the reader loop (e.g. a DecodeError from a malformed
                # packet). Either way, _reader_loop's own finally block has
                # already flushed pending requests with a suitable error, so we
                # only need to make sure that exception doesn't propagate out of
                # close() itself.
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await self._reader_task
                self._reader_task = None
            if self._ws:
                await self._ws.close()
                self._ws = None
            self._flush_pending(ConnectionError("client closed"))

    def _on_reader_task_done(self, task: "asyncio.Task[None]") -> None:
        """Retrieve/log the reader task's exception so it isn't lost.

        Without this, an unawaited task that finishes with an exception
        produces an "exception was never retrieved" warning from asyncio once
        it's garbage collected, since close() only awaits the task when it is
        the one calling cancel().
        """
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            _LOGGER.debug("dwarf_mini: reader loop terminated with error: %s", exc)

    def register_notification_handler(self, handler: NotificationHandler) -> None:
        self._notification_handlers.add(handler)

    def unregister_notification_handler(self, handler: NotificationHandler) -> None:
        self._notification_handlers.discard(handler)

    async def send_request(
        self,
        module_id: int,
        cmd: int,
        request_message: Message,
        response_cls: type[Message],
        *,
        timeout: float = 10.0,
    ) -> Message:
        await self.connect()
        assert self._ws is not None

        key = (module_id, cmd)
        if key in self._pending:
            raise RuntimeError(f"request for module {module_id} cmd {cmd} already pending")

        loop = asyncio.get_running_loop()
        future: "asyncio.Future[Message]" = loop.create_future()
        self._pending[key] = _PendingRequest(future=future, response_cls=response_cls)

        packet = WsPacket(
            major_version=1,
            minor_version=2,
            device_id=1,
            module_id=module_id,
            cmd=cmd,
            type=TYPE_REQUEST,
            data=request_message.SerializeToString(),
            client_id=self._client_id,
        )
        try:
            await self._ws.send_bytes(packet.SerializeToString())
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(key, None)

    async def _reader_loop(self) -> None:
        assert self._ws is not None
        # Whatever error pending requests should see once the loop ends. Stays
        # this default for a clean/normal disconnect and for cancellation;
        # overridden below if the loop dies on an unexpected exception.
        exc_to_flush: Exception = ConnectionError("connection closed")
        try:
            async for msg in self._ws:
                if msg.type != aiohttp.WSMsgType.BINARY:
                    continue
                packet = WsPacket()
                try:
                    packet.ParseFromString(msg.data)
                except DecodeError:
                    _LOGGER.debug("dwarf_mini: failed to decode packet")
                    continue
                await self._dispatch(packet)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # pragma: no cover - defensive
            _LOGGER.debug("dwarf_mini: reader loop failed: %s", exc)
            # Invalidate the connection so `connected` correctly reflects that
            # there is no live reader loop anymore, and so a subsequent
            # connect()/send_request() doesn't no-op against a dead socket.
            self._ws = None
            exc_to_flush = exc
            raise
        finally:
            # Runs on every exit path (normal loop end, CancelledError, or an
            # unexpected exception) so a pending send_request() fails promptly
            # instead of hanging until its timeout.
            self._flush_pending(exc_to_flush)

    async def _dispatch(self, packet: WsPacket) -> None:
        key = (packet.module_id, packet.cmd)
        if packet.type == TYPE_REQUEST_RESPONSE:
            pending = self._pending.get(key)
            if pending is not None and not pending.future.done():
                response = pending.response_cls()
                response.ParseFromString(packet.data)
                pending.future.set_result(response)
            else:
                _LOGGER.debug(
                    "dwarf_mini: received response for module %s cmd %s with no "
                    "matching pending request (already timed out?)",
                    packet.module_id,
                    packet.cmd,
                )
            return
        if packet.type == TYPE_NOTIFICATION:
            await asyncio.gather(
                *(handler(packet) for handler in list(self._notification_handlers)),
                return_exceptions=True,
            )

    def _flush_pending(self, error: Exception) -> None:
        for pending in self._pending.values():
            if not pending.future.done():
                pending.future.set_exception(error)
        self._pending.clear()
