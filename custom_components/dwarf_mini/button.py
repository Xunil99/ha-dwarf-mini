"""Button platform for DWARF mini."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DwarfMiniConfigEntry
from .client import DwarfMiniClient
from .const import (
    CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
    CMD_ASTRO_STOP_CAPTURE_RAW_LIVE_STACKING,
    DOMAIN,
    MODULE_ASTRO,
)
from .proto_messages import (
    ComResponse,
    ReqCaptureRawLiveStacking,
    ReqStopCaptureRawLiveStacking,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DwarfMiniConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client: DwarfMiniClient = entry.runtime_data
    async_add_entities(
        [
            DwarfMiniStartCaptureButton(client, entry),
            DwarfMiniStopCaptureButton(client, entry),
        ]
    )


class _DwarfMiniBaseButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(
        self, client: DwarfMiniClient, entry: DwarfMiniConfigEntry, key: str
    ) -> None:
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name="DWARF mini"
        )

    @staticmethod
    def _raise_if_rejected(response: ComResponse) -> None:
        """Turn a non-zero ComResponse.code into a user-visible HA error.

        send_request() only raises on a transport-level failure (timeout,
        disconnect) - a device-level rejection (e.g. CODE_ASTRO_FUNCTION_BUSY
        while the device is mid-calibration) comes back as a normal response
        with a non-zero `code` and would otherwise be silently discarded,
        leaving the user believing the press succeeded. Without a mapping
        from every known device error code to a specific message (out of
        scope for v1), surfacing the raw code is the best available signal.
        """
        if response.code != 0:
            raise HomeAssistantError(
                f"DWARF mini hat den Befehl abgelehnt (code={response.code})",
                translation_domain=DOMAIN,
                translation_key="capture_command_rejected",
                translation_placeholders={"code": str(response.code)},
            )


class DwarfMiniStartCaptureButton(_DwarfMiniBaseButton):
    _attr_translation_key = "start_capture"

    def __init__(self, client: DwarfMiniClient, entry: DwarfMiniConfigEntry) -> None:
        super().__init__(client, entry, "start_capture")

    async def async_press(self) -> None:
        # ir_index=1 ("Astro" mode, vs. 2 = "Duo-Band on DWARF mini") and
        # force_start=False (apply the device's own normal validation rather
        # than bypassing calibration/GOTO warnings) are fixed v1 defaults -
        # see the Task 10 plan for why. Not exposed as options: v1 has no
        # filter-selection UI and no GOTO-awareness.
        response = await self._client.send_request(
            MODULE_ASTRO,
            CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
            ReqCaptureRawLiveStacking(ir_index=1, force_start=False),
            ComResponse,
        )
        self._raise_if_rejected(response)


class DwarfMiniStopCaptureButton(_DwarfMiniBaseButton):
    _attr_translation_key = "stop_capture"

    def __init__(self, client: DwarfMiniClient, entry: DwarfMiniConfigEntry) -> None:
        super().__init__(client, entry, "stop_capture")

    async def async_press(self) -> None:
        response = await self._client.send_request(
            MODULE_ASTRO,
            CMD_ASTRO_STOP_CAPTURE_RAW_LIVE_STACKING,
            ReqStopCaptureRawLiveStacking(),
            ComResponse,
        )
        self._raise_if_rejected(response)
