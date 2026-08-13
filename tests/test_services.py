# tests/test_services.py
"""Tests for the dwarf_mini.goto_coordinates service (Phase 2 gap-closing task).

Mirrors test_select.py's DSO-branch tests (same underlying request shape,
same home-location guard) since this service is documented to reuse that
exact logic path - see custom_components/dwarf_mini/goto.py.
"""
import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

from custom_components.dwarf_mini.const import (
    CMD_ASTRO_START_ONE_CLICK_GOTO_DSO,
    DOMAIN,
    MODULE_ASTRO,
)
from custom_components.dwarf_mini.proto_messages import ReqOneClickGotoDSO, ResOneClickGoto


def _device_id(hass) -> str:
    """Return the device_id of the (single) DWARF mini device registered by
    the connected_client fixture's config entry."""
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    registry = dr.async_get(hass)
    device = registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None, "expected a DWARF mini device to be registered"
    return device.id


@pytest.mark.asyncio
async def test_service_is_registered_after_setup(hass, fake_dwarf_server, connected_client):
    assert hass.services.has_service(DOMAIN, "goto_coordinates")


@pytest.mark.asyncio
async def test_goto_coordinates_sends_correct_request(hass, fake_dwarf_server, connected_client):
    """Calling the service sends ReqOneClickGotoDSO with the given ra/dec/
    target_name and the current hass.config lat/lon - the same request shape
    select.py's DSO branch sends."""
    received = []

    def _handler(data: bytes) -> bytes:
        payload = ReqOneClickGotoDSO()
        payload.ParseFromString(data)
        received.append(payload)
        return ResOneClickGoto(step=1, code=0, all_end=False).SerializeToString()

    fake_dwarf_server.app["handlers"][
        (MODULE_ASTRO, CMD_ASTRO_START_ONE_CLICK_GOTO_DSO)
    ] = _handler

    await hass.services.async_call(
        DOMAIN,
        "goto_coordinates",
        {
            "device_id": _device_id(hass),
            "ra_hours": 12.34,
            "dec_degrees": -5.6,
            "target_name": "Free target",
        },
        blocking=True,
    )

    assert len(received) == 1
    assert received[0].ra == pytest.approx(12.34)
    assert received[0].dec == pytest.approx(-5.6)
    assert received[0].target_name == "Free target"
    assert received[0].lon == pytest.approx(hass.config.longitude)
    assert received[0].lat == pytest.approx(hass.config.latitude)


@pytest.mark.asyncio
async def test_goto_coordinates_defaults_target_name(hass, fake_dwarf_server, connected_client):
    """Omitting target_name falls back to an 'RA <h>h Dec <deg>°' label."""
    received = []

    def _handler(data: bytes) -> bytes:
        payload = ReqOneClickGotoDSO()
        payload.ParseFromString(data)
        received.append(payload)
        return ResOneClickGoto(step=1, code=0, all_end=False).SerializeToString()

    fake_dwarf_server.app["handlers"][
        (MODULE_ASTRO, CMD_ASTRO_START_ONE_CLICK_GOTO_DSO)
    ] = _handler

    await hass.services.async_call(
        DOMAIN,
        "goto_coordinates",
        {
            "device_id": _device_id(hass),
            "ra_hours": 1.5,
            "dec_degrees": 2.5,
        },
        blocking=True,
    )

    assert len(received) == 1
    assert received[0].target_name == "RA 1.5h Dec 2.5°"


@pytest.mark.asyncio
async def test_goto_coordinates_raises_when_home_location_not_configured(
    hass, fake_dwarf_server, connected_client
):
    """Same guard as select.py: an unconfigured (0.0/0.0) home location must
    raise before any request reaches the device."""
    hass.config.latitude = 0.0
    hass.config.longitude = 0.0

    received = []

    def _handler(data: bytes) -> bytes:
        received.append(data)
        return ResOneClickGoto(step=1, code=0, all_end=False).SerializeToString()

    fake_dwarf_server.app["handlers"][
        (MODULE_ASTRO, CMD_ASTRO_START_ONE_CLICK_GOTO_DSO)
    ] = _handler

    with pytest.raises(HomeAssistantError, match="Heimatort"):
        await hass.services.async_call(
            DOMAIN,
            "goto_coordinates",
            {
                "device_id": _device_id(hass),
                "ra_hours": 1.0,
                "dec_degrees": 2.0,
            },
            blocking=True,
        )

    assert received == [], "no GoTo request may reach the device with an unconfigured location"


@pytest.mark.asyncio
async def test_goto_coordinates_raises_on_device_rejection(
    hass, fake_dwarf_server, connected_client
):
    def _handler(data: bytes) -> bytes:
        return ResOneClickGoto(step=1, code=7, all_end=False).SerializeToString()

    fake_dwarf_server.app["handlers"][
        (MODULE_ASTRO, CMD_ASTRO_START_ONE_CLICK_GOTO_DSO)
    ] = _handler

    with pytest.raises(HomeAssistantError, match="7"):
        await hass.services.async_call(
            DOMAIN,
            "goto_coordinates",
            {
                "device_id": _device_id(hass),
                "ra_hours": 1.0,
                "dec_degrees": 2.0,
            },
            blocking=True,
        )
