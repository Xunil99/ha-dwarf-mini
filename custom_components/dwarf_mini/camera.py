"""Camera platform for DWARF mini (live view via MJPEG-over-HTTP)."""
from __future__ import annotations

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DwarfMiniConfigEntry
from .const import CONF_HOST, DOMAIN

STREAM_PORT = 8092


async def async_setup_entry(
    hass, entry: DwarfMiniConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    host = entry.data[CONF_HOST]
    async_add_entities(
        [
            DwarfMiniCamera(entry, "tele", "mainstream", host),
            DwarfMiniCamera(entry, "wide", "thirdstream", host),
        ]
    )


class DwarfMiniCamera(Camera):
    """MJPEG-over-HTTP live-view camera.

    The camera platform originally used RTSP URLs
    (rtsp://<host>:554/ch0|ch1/stream0), which tested fine directly in VLC but
    turned out not to be reliable/correct once deployed against a real Home
    Assistant instance. Real-world HA testing on 2026-08-13 confirmed the
    actual working endpoints are plain HTTP MJPEG streams on port 8092:
    http://<host>:8092/mainstream (tele) and http://<host>:8092/thirdstream
    (wide) - not RTSP on port 554 with ch0/ch1/stream0 paths. Port 8092 also
    corroborates earlier research: dwarfAlp's DwarfHttpClient documents
    jpeg_port: int = 8092 as a real, separate port for JPEG/image content on
    this device family.

    HA's built-in Generic Camera integration
    (homeassistant/components/generic/camera.py) sets the same
    CameraEntityFeature.STREAM and uses the same stream_source() mechanism for
    both RTSP and MJPEG-over-HTTP sources, so this class's architecture
    (Camera subclass, CameraEntityFeature.STREAM, stream_source() override)
    did not need to change - only the URL template did.
    """

    _attr_has_entity_name = True
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, entry: DwarfMiniConfigEntry, key: str, stream_name: str, host: str) -> None:
        super().__init__()
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}_camera"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name="DWARF mini"
        )
        self._stream_url = f"http://{host}:{STREAM_PORT}/{stream_name}"

    async def stream_source(self) -> str | None:
        return self._stream_url
