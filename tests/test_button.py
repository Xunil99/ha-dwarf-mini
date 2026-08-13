# tests/test_button.py
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.dwarf_mini.const import (
    CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
    CMD_ASTRO_STOP_CAPTURE_RAW_LIVE_STACKING,
    MODULE_ASTRO,
)
from custom_components.dwarf_mini.proto_messages import (
    ComResponse,
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
