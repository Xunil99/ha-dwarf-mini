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
    CMD_ASTRO_STOP_ONE_CLICK_GOTO,
    CMD_FOCUS_START_ASTRO_AUTO_FOCUS,
    DOMAIN,
    MODULE_ASTRO,
    MODULE_FOCUS,
)
from .proto_messages import (
    ComResponse,
    ReqAstroAutoFocus,
    ReqCaptureRawLiveStacking,
    ReqStopCaptureRawLiveStacking,
    ReqStopOneClickGoto,
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
            DwarfMiniStopGotoButton(client, entry),
            DwarfMiniAutofocusButton(client, entry),
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
                f"DWARF mini rejected the command (code={response.code})",
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


class DwarfMiniStopGotoButton(_DwarfMiniBaseButton):
    _attr_translation_key = "stop_goto"

    def __init__(self, client: DwarfMiniClient, entry: DwarfMiniConfigEntry) -> None:
        super().__init__(client, entry, "stop_goto")

    async def async_press(self) -> None:
        # CMD_ASTRO_STOP_ONE_CLICK_GOTO's response type: astro.proto defines
        # no dedicated "ResStopOneClickGoto" message (the message immediately
        # after ReqStopOneClickGoto is the unrelated
        # ReqCaptureWideRawLiveStacking, not a stop-specific response), and
        # this codebase's proto_messages.py mirrors that gap. ComResponse is
        # verified correct here against dwarfAlp's own implementation:
        # session.py's telescope_abort_slew() sends ReqStopOneClickGoto()
        # with no expected_responses override, which falls back to
        # ws_client.py's send_and_check()/send_command() default of
        # ComResponse. ResOneClickGoto (step/code/all_end) is used
        # exclusively for the start path (multi-phase slew progress), never
        # for stop.
        response = await self._client.send_request(
            MODULE_ASTRO,
            CMD_ASTRO_STOP_ONE_CLICK_GOTO,
            ReqStopOneClickGoto(),
            ComResponse,
        )
        self._raise_if_rejected(response)


class DwarfMiniAutofocusButton(_DwarfMiniBaseButton):
    _attr_translation_key = "autofocus"

    def __init__(self, client: DwarfMiniClient, entry: DwarfMiniConfigEntry) -> None:
        super().__init__(client, entry, "autofocus")

    async def async_press(self) -> None:
        # mode=1 is a fixed v1 default per the phase 2 design doc
        # (ReqAstroAutoFocus{mode: uint32=1}), matching the other buttons'
        # fixed-default pattern - v1 has no autofocus-mode-selection UI.
        #
        # timeout=30.0 instead of send_request()'s plain 10s default:
        # dwarfAlp's own session.py explicitly avoids the plain default for
        # this exact command too - _autofocus_before_calibration() uses a
        # much longer, configurable calibration_autofocus_timeout_seconds
        # instead, with a comment noting the command ack is only a
        # confirmation and the real autofocus completion arrives later via
        # the V3ResNotifyAutoFocusState notification (state=3) - i.e. the
        # device-side ack for this specific command is known to sometimes
        # lag past a plain 10s bound.
        response = await self._client.send_request(
            MODULE_FOCUS,
            CMD_FOCUS_START_ASTRO_AUTO_FOCUS,
            ReqAstroAutoFocus(mode=1),
            ComResponse,
            timeout=30.0,
        )
        self._raise_if_rejected(response)
