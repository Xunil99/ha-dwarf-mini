# tests/test_button.py
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.dwarf_mini.const import (
    CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
    CMD_ASTRO_STOP_CAPTURE_RAW_LIVE_STACKING,
    CMD_ASTRO_STOP_ONE_CLICK_GOTO,
    CMD_FOCUS_START_ASTRO_AUTO_FOCUS,
    MODULE_ASTRO,
    MODULE_FOCUS,
)
from custom_components.dwarf_mini.proto_messages import (
    ComResponse,
    ReqAstroAutoFocus,
    ReqCaptureRawLiveStacking,
)


@pytest.mark.asyncio
async def test_start_capture_button(hass, fake_dwarf_server, connected_client):
    """Pressing the start-capture button sends the fixed v1 start request.

    Registers a handler on the fake server for
    (MODULE_ASTRO, CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING) that decodes
    the payload it actually received and records it, so the assertion below
    proves the button sent the right (module_id, cmd) *and* the right
    ir_index=1/force_start=False payload - not just that async_press()
    didn't raise.
    """
    received = []

    def _handler(data: bytes) -> bytes:
        payload = ReqCaptureRawLiveStacking()
        payload.ParseFromString(data)
        received.append(payload)
        return ComResponse(code=0).SerializeToString()

    fake_dwarf_server.app["handlers"][
        (MODULE_ASTRO, CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING)
    ] = _handler

    state = hass.states.get("button.dwarf_mini_start_capture")
    assert state is not None

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.dwarf_mini_start_capture"},
        blocking=True,
    )

    assert len(received) == 1
    assert received[0].ir_index == 1
    assert received[0].force_start is False


@pytest.mark.asyncio
async def test_stop_capture_button(hass, fake_dwarf_server, connected_client):
    """Pressing the stop-capture button sends a request to the stop cmd.

    The stop request message has no fields, so there's nothing to decode -
    the handler being invoked at all (with the right module_id/cmd key) is
    the proof that the button sent the correct request.
    """
    call_count = 0

    def _handler(data: bytes) -> bytes:
        nonlocal call_count
        call_count += 1
        return ComResponse(code=0).SerializeToString()

    fake_dwarf_server.app["handlers"][
        (MODULE_ASTRO, CMD_ASTRO_STOP_CAPTURE_RAW_LIVE_STACKING)
    ] = _handler

    state = hass.states.get("button.dwarf_mini_stop_capture")
    assert state is not None

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.dwarf_mini_stop_capture"},
        blocking=True,
    )

    assert call_count == 1


@pytest.mark.asyncio
async def test_start_capture_button_raises_when_device_rejects(
    hass, fake_dwarf_server, connected_client
):
    """A non-zero ComResponse.code (e.g. CODE_ASTRO_FUNCTION_BUSY while the
    device is mid-calibration) must surface as a visible HA error, not be
    silently discarded - the whole point of this test is proving the code
    actually gets checked, not just that a response was received.
    """

    def _handler(data: bytes) -> bytes:
        return ComResponse(code=13).SerializeToString()

    fake_dwarf_server.app["handlers"][
        (MODULE_ASTRO, CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING)
    ] = _handler

    with pytest.raises(HomeAssistantError, match="13"):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.dwarf_mini_start_capture"},
            blocking=True,
        )


@pytest.mark.asyncio
async def test_stop_capture_button_raises_when_device_rejects(
    hass, fake_dwarf_server, connected_client
):
    """Same rejection check as the start-capture test above, for stop."""

    def _handler(data: bytes) -> bytes:
        return ComResponse(code=7).SerializeToString()

    fake_dwarf_server.app["handlers"][
        (MODULE_ASTRO, CMD_ASTRO_STOP_CAPTURE_RAW_LIVE_STACKING)
    ] = _handler

    with pytest.raises(HomeAssistantError, match="7"):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.dwarf_mini_stop_capture"},
            blocking=True,
        )


@pytest.mark.asyncio
async def test_start_capture_button_propagates_transport_failure(
    hass, connected_client
):
    """A transport-level failure (timeout/disconnect) during send_request()
    must propagate out of the button press, not be swallowed - proven here
    by patching the real connected client's send_request (the same instance
    the entity holds via entry.runtime_data) to raise, rather than merely
    asserting this in prose.
    """
    with patch.object(
        connected_client, "send_request", AsyncMock(side_effect=ConnectionError("boom"))
    ):
        with pytest.raises(ConnectionError, match="boom"):
            await hass.services.async_call(
                "button",
                "press",
                {"entity_id": "button.dwarf_mini_start_capture"},
                blocking=True,
            )


@pytest.mark.asyncio
async def test_stop_capture_button_propagates_transport_failure(
    hass, connected_client
):
    """Transport-failure propagation check for the stop button, mirroring
    test_start_capture_button_propagates_transport_failure above."""
    with patch.object(
        connected_client, "send_request", AsyncMock(side_effect=ConnectionError("boom"))
    ):
        with pytest.raises(ConnectionError, match="boom"):
            await hass.services.async_call(
                "button",
                "press",
                {"entity_id": "button.dwarf_mini_stop_capture"},
                blocking=True,
            )


@pytest.mark.asyncio
async def test_stop_goto_button(hass, fake_dwarf_server, connected_client):
    """Pressing the stop-goto button sends a request to the stop-goto cmd.

    ReqStopOneClickGoto has no fields, so - as with
    test_stop_capture_button above - the handler being invoked at all (with
    the right module_id/cmd key) is the proof that the button sent the
    correct request.
    """
    call_count = 0

    def _handler(data: bytes) -> bytes:
        nonlocal call_count
        call_count += 1
        return ComResponse(code=0).SerializeToString()

    fake_dwarf_server.app["handlers"][
        (MODULE_ASTRO, CMD_ASTRO_STOP_ONE_CLICK_GOTO)
    ] = _handler

    state = hass.states.get("button.dwarf_mini_stop_goto")
    assert state is not None

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.dwarf_mini_stop_goto"},
        blocking=True,
    )

    assert call_count == 1


@pytest.mark.asyncio
async def test_stop_goto_button_raises_when_device_rejects(
    hass, fake_dwarf_server, connected_client
):
    """Same rejection check as the capture-button tests above, for stop-goto."""

    def _handler(data: bytes) -> bytes:
        return ComResponse(code=5).SerializeToString()

    fake_dwarf_server.app["handlers"][
        (MODULE_ASTRO, CMD_ASTRO_STOP_ONE_CLICK_GOTO)
    ] = _handler

    with pytest.raises(HomeAssistantError, match="5"):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.dwarf_mini_stop_goto"},
            blocking=True,
        )


@pytest.mark.asyncio
async def test_stop_goto_button_propagates_transport_failure(hass, connected_client):
    """Transport-failure propagation check for the stop-goto button, mirroring
    test_start_capture_button_propagates_transport_failure above."""
    with patch.object(
        connected_client, "send_request", AsyncMock(side_effect=ConnectionError("boom"))
    ):
        with pytest.raises(ConnectionError, match="boom"):
            await hass.services.async_call(
                "button",
                "press",
                {"entity_id": "button.dwarf_mini_stop_goto"},
                blocking=True,
            )


@pytest.mark.asyncio
async def test_autofocus_button(hass, fake_dwarf_server, connected_client):
    """Pressing the autofocus button sends the fixed v1 autofocus request.

    Registers a handler on the fake server for
    (MODULE_FOCUS, CMD_FOCUS_START_ASTRO_AUTO_FOCUS) that decodes the
    payload it actually received and records it, so the assertion below
    proves the button sent the right (module_id, cmd) *and* the right
    mode=1 payload - not just that async_press() didn't raise.
    """
    received = []

    def _handler(data: bytes) -> bytes:
        payload = ReqAstroAutoFocus()
        payload.ParseFromString(data)
        received.append(payload)
        return ComResponse(code=0).SerializeToString()

    fake_dwarf_server.app["handlers"][
        (MODULE_FOCUS, CMD_FOCUS_START_ASTRO_AUTO_FOCUS)
    ] = _handler

    state = hass.states.get("button.dwarf_mini_autofocus")
    assert state is not None

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.dwarf_mini_autofocus"},
        blocking=True,
    )

    assert len(received) == 1
    assert received[0].mode == 1


@pytest.mark.asyncio
async def test_autofocus_button_raises_when_device_rejects(
    hass, fake_dwarf_server, connected_client
):
    """Same rejection check as the capture-button tests above, for autofocus."""

    def _handler(data: bytes) -> bytes:
        return ComResponse(code=9).SerializeToString()

    fake_dwarf_server.app["handlers"][
        (MODULE_FOCUS, CMD_FOCUS_START_ASTRO_AUTO_FOCUS)
    ] = _handler

    with pytest.raises(HomeAssistantError, match="9"):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.dwarf_mini_autofocus"},
            blocking=True,
        )


@pytest.mark.asyncio
async def test_autofocus_button_propagates_transport_failure(hass, connected_client):
    """Transport-failure propagation check for the autofocus button, mirroring
    test_start_capture_button_propagates_transport_failure above."""
    with patch.object(
        connected_client, "send_request", AsyncMock(side_effect=ConnectionError("boom"))
    ):
        with pytest.raises(ConnectionError, match="boom"):
            await hass.services.async_call(
                "button",
                "press",
                {"entity_id": "button.dwarf_mini_autofocus"},
                blocking=True,
            )


@pytest.mark.asyncio
async def test_autofocus_button_requests_extended_timeout(hass, connected_client):
    """The autofocus button must not rely on send_request()'s plain 10s
    default: dwarfAlp's own session.py explicitly avoids the default for
    this exact command (_autofocus_before_calibration() uses a much longer,
    configurable timeout instead), because the command ack is only a
    confirmation and can lag - the real autofocus completion arrives later
    via a separate notification. Asserts the actual kwarg value passed to
    send_request(), so a regression back to the plain default would be
    caught here even though it wouldn't cause a fast-mocked test to fail on
    its own.
    """
    mock_send_request = AsyncMock(return_value=ComResponse(code=0))
    with patch.object(connected_client, "send_request", mock_send_request):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.dwarf_mini_autofocus"},
            blocking=True,
        )

    assert mock_send_request.await_args.kwargs["timeout"] == 30.0


@pytest.mark.asyncio
async def test_autofocus_button_tolerates_slow_but_acceptable_response(
    hass, connected_client
):
    """A device ack that takes a bit to arrive (still well within the
    extended timeout) must not fail the button press - proving async_press()
    itself doesn't impose any additional, shorter wait on top of whatever
    send_request() is given, which would otherwise silently undercut the
    extended timeout=30.0 fix.
    """

    async def _slow_ack(*args, **kwargs):
        await asyncio.sleep(0.2)
        return ComResponse(code=0)

    with patch.object(connected_client, "send_request", AsyncMock(side_effect=_slow_ack)):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.dwarf_mini_autofocus"},
            blocking=True,
        )
