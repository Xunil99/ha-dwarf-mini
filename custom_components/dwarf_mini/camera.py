"""Camera platform for DWARF mini (live view via RTSP)."""
from __future__ import annotations

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DwarfMiniConfigEntry
from .const import CONF_HOST, DOMAIN

RTSP_PORT = 554


async def async_setup_entry(
    hass, entry: DwarfMiniConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    host = entry.data[CONF_HOST]
    async_add_entities(
        [
            DwarfMiniCamera(entry, "tele", "ch0", host),
            DwarfMiniCamera(entry, "wide", "ch1", host),
        ]
    )


class DwarfMiniCamera(Camera):
    """RTSP live-view camera.

    URL scheme (rtsp://<host>:554/ch0|ch1/stream0) confirmed working against real
    DWARF mini hardware 2026-08-13; matches the URL pattern used by the (unrelated,
    independently-sourced) dwarflab-viewer project for the same device family - we
    only reuse the URL structure (a protocol fact), not any of its code.
    """

    _attr_has_entity_name = True
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, entry: DwarfMiniConfigEntry, key: str, channel: str, host: str) -> None:
        super().__init__()
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}_camera"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name="DWARF mini"
        )
        self._rtsp_url = f"rtsp://{host}:{RTSP_PORT}/{channel}/stream0"

    async def stream_source(self) -> str | None:
        return self._rtsp_url
