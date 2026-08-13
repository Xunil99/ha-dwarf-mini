"""Select platform for DWARF mini (GoTo target picker)."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DwarfMiniConfigEntry
from .client import DwarfMiniClient
from .const import (
    CMD_ASTRO_START_ONE_CLICK_GOTO_SOLAR_SYSTEM,
    DOMAIN,
    GOTO_DSO_TARGETS,
    GOTO_SOLAR_SYSTEM_TARGETS,
    MODULE_ASTRO,
)
from .goto import async_goto_dso, require_home_location
from .proto_messages import ReqOneClickGotoSolarSystem, ResOneClickGoto

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: DwarfMiniConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    async_add_entities([DwarfMiniGotoTargetSelect(hass, client, entry)])


class DwarfMiniGotoTargetSelect(SelectEntity):
    """GoTo target picker.

    Options are the union of GOTO_DSO_TARGETS (verified
    ReqOneClickGotoDSO path) and GOTO_SOLAR_SYSTEM_TARGETS (UNVERIFIED
    ReqOneClickGotoSolarSystem path - dwarfAlp never exercises this command
    on real hardware, only the message shape and enum values are known from
    the .proto sources; see const.py). The solar-system option labels carry
    an explicit "(experimentell)" suffix so this is visible in the dropdown
    itself, not just in source comments - a mis-parsed/mis-encoded
    unverified GoTo that slews the optics onto the Sun is a potential
    sensor-damage risk (not merely cosmetic) if the device firmware doesn't
    itself guard against it, which is unknown to us. Do not remove that
    suffix or otherwise make solar-system options visually indistinguishable
    from the verified DSO targets without re-verifying the whole path
    against real hardware first.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "goto_target"

    def __init__(self, hass: HomeAssistant, client: DwarfMiniClient, entry: DwarfMiniConfigEntry) -> None:
        self._hass = hass
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_goto_target"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name="DWARF mini"
        )
        self._attr_options = list(GOTO_DSO_TARGETS) + list(GOTO_SOLAR_SYSTEM_TARGETS)
        self._attr_current_option = None

    async def async_select_option(self, option: str) -> None:
        if option in GOTO_DSO_TARGETS:
            ra, dec = GOTO_DSO_TARGETS[option]
            # Shared with the dwarf_mini.goto_coordinates service (see
            # goto.py's module docstring) - including the home-location
            # guard, so this branch and the service can't drift apart on it.
            await async_goto_dso(self._hass, self._client, ra=ra, dec=dec, target_name=option)
        elif option in GOTO_SOLAR_SYSTEM_TARGETS:
            # Same home-location guard as the DSO path above (shared
            # function, not a re-implementation) - the unverified
            # solar-system path needs it just as much as the verified one.
            lon, lat = require_home_location(self._hass)
            index = GOTO_SOLAR_SYSTEM_TARGETS[option]
            request = ReqOneClickGotoSolarSystem(
                index=index,
                lon=lon,
                lat=lat,
                target_name=option,
                # Same fixed v1 defaults as the DSO branch above:
                # shooting_mode=2 (astro live-stacking) and force_start=False
                # (apply the device's own normal validation instead of
                # bypassing calibration/GOTO warnings, matching
                # button.py's force_start=False).
                shooting_mode=2,
                force_start=False,
            )
            cmd = CMD_ASTRO_START_ONE_CLICK_GOTO_SOLAR_SYSTEM
            _LOGGER.debug(
                "Sending GoTo request for %s (module=%s cmd=%s)", option, MODULE_ASTRO, cmd
            )
            response = await self._client.send_request(MODULE_ASTRO, cmd, request, ResOneClickGoto)
            if response.code != 0:
                _LOGGER.warning(
                    "DWARF mini rejected GoTo to %s (code=%s)", option, response.code
                )
                raise HomeAssistantError(
                    f"DWARF mini rejected GoTo to {option} (code={response.code})"
                )
        else:
            raise HomeAssistantError(f"Unknown GoTo target: {option}")

        self._attr_current_option = option
        self.async_write_ha_state()
