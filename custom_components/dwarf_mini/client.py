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

from .const import (
    AUTOFOCUS_STATE_COMPLETE,
    AUTOFOCUS_STATE_RUNNING,
    CMD_NOTIFY_ELE,
    CMD_NOTIFY_FOCUS,
    CMD_NOTIFY_PROGRASS_CAPTURE_RAW_LIVE_STACKING,
    CMD_NOTIFY_STATE_ASTRO_ONE_CLICK_GOTO,
    CMD_NOTIFY_STATE_CAPTURE_RAW_LIVE_STACKING,
    CMD_SYSTEM_SET_MASTERLOCK,
    CMD_V3_NOTIFY_AUTOFOCUS_STATE,
    CMD_V3_NOTIFY_AUTOFOCUS_STATE_ALT,
    MODULE_SYSTEM,
    OPERATION_STATE_NAMES,
    STATE_RUNNING,
)
from .proto_messages import (
    ComResponse,
    ComResWithInt,
    ReqsetMasterLock,
    ResNotifyFocus,
    ResNotifyOneClickGotoState,
    ResNotifyProgressCaptureRawLiveStacking,
    TYPE_NOTIFICATION,
    TYPE_REQUEST,
    TYPE_REQUEST_RESPONSE,
    V3ResNotifyAutoFocusState,
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
        reconnect_initial_delay: float = 5.0,
        reconnect_max_delay: float = 60.0,
    ) -> None:
        self._session = session
        self._ws_url = ws_url
        self._client_id = client_id
        # Configurable so tests can exercise run_forever()'s backoff/close
        # interaction without waiting out the real 5s/60s delays.
        self._reconnect_initial_delay = reconnect_initial_delay
        self._reconnect_max_delay = reconnect_max_delay

        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._pending: dict[tuple[int, int], _PendingRequest] = {}
        self._notification_handlers: set[NotificationHandler] = set()
        self._lock = asyncio.Lock()
        # Set by close() and checked by run_forever() so a deliberate shutdown
        # doesn't race with the reconnect loop — see run_forever()'s docstring.
        # An Event (not a plain bool) so run_forever() can wake up from its
        # backoff sleep immediately when close() is called, instead of
        # discovering the shutdown only after the sleep finishes on its own.
        self._closing_event = asyncio.Event()

        self._listeners: set[Callable[[], None]] = set()
        self.state: dict[str, Any] = {
            "battery_percent": None,
            "capture_state": None,
            "progress_current": None,
            "progress_total": None,
            "progress_stacked": None,
            "focus_position": None,
            "autofocus_state": None,        # "running" / "complete" / "unrecognized"
            "goto_state": None,              # OPERATION_STATE_NAMES-style value
            "goto_target_name": None,
            "tracking": False,
        }
        self.register_notification_handler(self._handle_notification)

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    async def connect(self) -> None:
        # An explicit connect() call means "be connected" — undo any prior
        # close()-initiated shutdown intent so run_forever() (if restarted by
        # the caller) is allowed to reconnect again instead of exiting.
        self._closing_event.clear()
        if self.connected:
            return
        async with self._lock:
            if self.connected:
                return
            self._ws = await self._session.ws_connect(self._ws_url, heartbeat=None)
            self._reader_task = asyncio.create_task(self._reader_loop())
            self._reader_task.add_done_callback(self._on_reader_task_done)
        # Deliberately *outside* the `async with self._lock:` block above (and
        # only reached when this call is the one that just established the
        # connection - both early `if self.connected: return`s above skip it):
        # _claim_master_lock() calls send_request(), which itself calls
        # `await self.connect()` at its start. self._lock is not reentrant,
        # so calling this from inside the lock would deadlock (or at best
        # cause confusing re-entry). By the time we get here `self._ws` and
        # `self._reader_task` are already set and the lock is free, so that
        # inner connect() call just hits the `if self.connected: return`
        # fast path above and send_request() can proceed normally.
        try:
            await self._claim_master_lock()
        except asyncio.CancelledError:
            # connect() itself got cancelled while the best-effort
            # master-lock claim above was still in flight - e.g. config_flow's
            # connectivity probe wraps this whole call in
            # `asyncio.wait_for(client.connect(), timeout=CONNECT_TIMEOUT)`,
            # and CONNECT_TIMEOUT (10s) is shorter than the claim's own
            # send_request() timeout (15s), so a device that's slow/
            # unresponsive to the claim (e.g. another client currently holds
            # it) gets its claim cancelled by the outer timeout before it can
            # finish. `_claim_master_lock()`'s own `except Exception` doesn't
            # catch this - CancelledError is a BaseException, not an
            # Exception, precisely so it isn't accidentally swallowed by
            # ordinary error handling - so it has to be handled here instead.
            #
            # The websocket itself already connected successfully (`self._ws`
            # and `self._reader_task` were set above, before this claim ever
            # ran), so this is treated the same as any other best-effort
            # master-lock failure: logged, not raised. Letting the
            # CancelledError escape connect() here would make an outer
            # `asyncio.wait_for` report this as connect() having failed
            # (converting the cancellation into `asyncio.TimeoutError`) even
            # though the connection is actually up - misreporting "cannot
            # connect" to the config_flow user for a device that IS reachable,
            # and worse, leaking the open websocket + reader task: the caller,
            # believing connect() failed, has no reason to call close() on a
            # client it thinks never connected.
            # See test_connect_outer_cancellation_during_master_lock_claim_
            # still_connects in test_client.py.
            _LOGGER.debug(
                "dwarf_mini: master-lock claim cancelled (likely an outer "
                "timeout); websocket connection itself is still established"
            )

    async def _claim_master_lock(self) -> None:
        """Best-effort: tell the device this client is now its active controller.

        The device does not push most state notifications (battery, capture state,
        ...) to a websocket client until it has claimed the "master lock" via
        CMD_SYSTEM_SET_MASTERLOCK - ported from dwarfAlp's session.py
        `_ensure_master_lock` (https://github.com/acocalypso/dwarfAlp, GPLv3).
        Failure here is logged, not raised: this runs on every connect() call,
        including short-lived connectivity-probe connections (e.g. the config
        flow's), which should still be able to report "reachable" even if another
        client currently holds the lock.
        """
        try:
            response = await self.send_request(
                MODULE_SYSTEM,
                CMD_SYSTEM_SET_MASTERLOCK,
                ReqsetMasterLock(lock=True),
                ComResponse,
                timeout=15.0,
            )
            if response.code != 0:
                _LOGGER.warning(
                    "dwarf_mini: master lock request rejected (code=%s)", response.code
                )
        except Exception:  # noqa: BLE001 - any failure here must not break connect()
            _LOGGER.warning("dwarf_mini: failed to claim master lock", exc_info=True)

    async def close(self) -> None:
        # Signal run_forever() (if a caller is running it as a background
        # task) to stop reconnecting instead of racing to re-establish the
        # connection this close() is tearing down. See run_forever().
        self._closing_event.set()
        async with self._lock:
            # Close (and null out) `_ws` *before* cancelling/awaiting the
            # reader task, not after: if run_forever() is running as a
            # separate task and also awaiting this same `_reader_task`, both
            # awaiters' resumptions get scheduled together once it's done -
            # run_forever()'s often runs first, since it started awaiting
            # earlier and so was registered as a callback first. If `_ws`
            # were still non-None at that point, `connected` would briefly
            # read True again from inside run_forever()'s post-disconnect
            # `_notify_listeners()` call, handing any listener a stale
            # "still connected" notification with no follow-up correction.
            # Clearing `_ws` first makes `connected` correctly read False no
            # matter which awaiter's continuation the event loop happens to
            # run first. See test_close_while_connected_does_not_send_stale_
            # connected_notification in test_client.py for the exact race.
            #
            # Not reachable through any call site in this codebase today:
            # async_unload_entry() only calls close() after
            # async_unload_platforms() has already torn down the
            # binary_sensor entity (and with it, its listener), and
            # config_flow.py's probe client never registers a listener at
            # all. This is future-proofing rather than a fix for an
            # observed production bug - kept because a later caller (e.g. a
            # reconnect service, or a reconfigure flow reusing a live
            # client) could plausibly call close() while listeners are still
            # attached, and this ordering is the correct/robust one
            # regardless.
            if self._ws:
                await self._ws.close()
                self._ws = None
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

    def add_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(callback)
        return lambda: self._listeners.discard(callback)

    def _notify_listeners(self) -> None:
        # Isolate each callback: one misbehaving listener raising must not
        # stop the remaining (possibly unrelated) listeners from being
        # notified.
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:  # pragma: no cover - defensive
                _LOGGER.warning("dwarf_mini: listener callback raised", exc_info=True)

    async def _handle_notification(self, packet: WsPacket) -> None:
        if packet.cmd == CMD_NOTIFY_ELE:
            value = ComResWithInt()
            try:
                value.ParseFromString(packet.data)
            except DecodeError:
                _LOGGER.debug(
                    "dwarf_mini: failed to decode notification payload (cmd=%s)", packet.cmd
                )
                return
            self.state["battery_percent"] = max(0, min(100, value.value))
            self._notify_listeners()
        elif packet.cmd == CMD_NOTIFY_STATE_CAPTURE_RAW_LIVE_STACKING:
            value = ComResWithInt()
            if packet.data:
                try:
                    value.ParseFromString(packet.data)
                except DecodeError:
                    _LOGGER.debug(
                        "dwarf_mini: failed to decode notification payload (cmd=%s)", packet.cmd
                    )
                    return
            # "unrecognized", not "unknown": HA's state machine already uses
            # "unknown" as its own reserved state for "no value received
            # yet" (see DwarfMiniCaptureStateSensor.native_value returning
            # None before the first notification). Falling back to that same
            # string here would make a genuinely-unrecognized device value
            # indistinguishable from cold start instead of standing out as
            # an anomaly.
            self.state["capture_state"] = OPERATION_STATE_NAMES.get(
                value.value, "unrecognized"
            )
            self._notify_listeners()
        elif packet.cmd == CMD_NOTIFY_PROGRASS_CAPTURE_RAW_LIVE_STACKING:
            progress = ResNotifyProgressCaptureRawLiveStacking()
            try:
                progress.ParseFromString(packet.data)
            except DecodeError:
                _LOGGER.debug(
                    "dwarf_mini: failed to decode notification payload (cmd=%s)", packet.cmd
                )
                return
            self.state["progress_current"] = progress.current_count
            self.state["progress_total"] = progress.total_count
            self.state["progress_stacked"] = progress.stacked_count
            self._notify_listeners()
        elif packet.cmd == CMD_NOTIFY_FOCUS:
            try:
                value = ResNotifyFocus()
                value.ParseFromString(packet.data)
            except DecodeError:
                _LOGGER.debug("dwarf_mini: failed to decode focus notification")
                return
            self.state["focus_position"] = value.focus
            self._notify_listeners()
        elif packet.cmd in (CMD_V3_NOTIFY_AUTOFOCUS_STATE, CMD_V3_NOTIFY_AUTOFOCUS_STATE_ALT):
            try:
                value = V3ResNotifyAutoFocusState()
                value.ParseFromString(packet.data)
            except DecodeError:
                _LOGGER.debug("dwarf_mini: failed to decode autofocus-state notification")
                return
            self.state["autofocus_state"] = {
                AUTOFOCUS_STATE_RUNNING: "running",
                AUTOFOCUS_STATE_COMPLETE: "complete",
            }.get(value.state, "unrecognized")
            self._notify_listeners()
        elif packet.cmd == CMD_NOTIFY_STATE_ASTRO_ONE_CLICK_GOTO:
            try:
                value = ResNotifyOneClickGotoState()
                value.ParseFromString(packet.data)
            except DecodeError:
                _LOGGER.debug("dwarf_mini: failed to decode one-click-goto notification")
                return
            self.state["goto_state"] = OPERATION_STATE_NAMES.get(value.state, "unrecognized")
            self.state["goto_target_name"] = value.goto_state.target_name or None
            self.state["tracking"] = value.tracking_state.state == STATE_RUNNING
            self._notify_listeners()

    async def run_forever(self) -> None:
        """Keep the connection alive, reconnecting with exponential backoff.

        Both a reader-loop *exception* (e.g. a DecodeError) and a *clean*
        disconnect (the server closes the socket; `_reader_loop`'s `async
        for` simply ends and the task completes with no exception at all)
        must trigger a backoff-and-retry here — a clean disconnect is in fact
        the common case (Wi-Fi drop, device sleep), so it cannot be left
        unhandled. `close()` cancelling `_reader_task` is a third case:
        `_reader_loop` catches and swallows `CancelledError` itself, so that
        task, too, completes with no exception. All three therefore need the
        same post-await handling below, gated by `self._closing_event` so a
        deliberate close() makes this loop exit instead of immediately
        reconnecting to the socket close() just tore down.

        The backoff wait itself is `self._closing_event.wait()` under a
        timeout rather than a plain `asyncio.sleep(delay)`: a bare sleep
        cannot be interrupted, so a close() arriving mid-backoff would only
        be noticed once the full (up to `reconnect_max_delay`) delay
        elapsed — defeating the point of the event. Waiting on the event
        lets close() wake this loop immediately, while a timeout (no
        close() during the wait) behaves exactly like the plain sleep did.

        Listener notification: `_notify_listeners()` is called after every
        successful (re)connect, and again after every disconnect (whether
        from an exception, a clean close by the peer, or our own close()).
        This is what lets a push-only consumer — e.g. a future
        `binary_sensor` reflecting `client.connected` — learn about
        connectivity changes without polling. `client.connected` is already
        the single source of truth for that state; there's no separate
        `state["connected"]` key to keep in sync, `_notify_listeners()` here
        is purely the event trigger.
        """
        delay = self._reconnect_initial_delay
        while not self._closing_event.is_set():
            try:
                await self.connect()
                self._notify_listeners()  # connectivity (re)established
                delay = self._reconnect_initial_delay
                assert self._reader_task is not None
                await self._reader_task
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - network dependent
                _LOGGER.warning(
                    "dwarf_mini: connection lost (%s), retrying in %.0fs", exc, delay
                )
            else:
                if not self._closing_event.is_set():
                    _LOGGER.warning(
                        "dwarf_mini: connection closed, retrying in %.0fs", delay
                    )

            self._notify_listeners()  # connectivity lost (error, clean, or close())

            if self._closing_event.is_set():
                break

            try:
                await asyncio.wait_for(self._closing_event.wait(), timeout=delay)
                break  # close() was called while we were waiting out the backoff
            except asyncio.TimeoutError:
                pass  # backoff elapsed normally; go around and try to reconnect
            delay = min(delay * 2, self._reconnect_max_delay)
