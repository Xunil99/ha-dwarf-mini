# custom_components/dwarf_mini/goto.py
"""Shared GoTo-DSO request logic.

Both the `select.dwarf_mini_goto_target` entity's DSO branch (select.py) and
the `dwarf_mini.goto_coordinates` service (registered in __init__.py) send the
exact same verified request shape (design doc section 3: `ReqOneClickGotoDSO`
via MODULE_ASTRO/CMD_ASTRO_START_ONE_CLICK_GOTO_DSO). Kept in one place -
including the home-location safety guard - so the two call sites can't
silently drift apart on it. That guard specifically exists for a real reason
(see require_home_location()'s docstring); duplicating it independently in
two files would risk exactly the kind of drift this module prevents.
"""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .client import DwarfMiniClient
from .const import CMD_ASTRO_START_ONE_CLICK_GOTO_DSO, MODULE_ASTRO
from .proto_messages import ReqOneClickGotoDSO, ResOneClickGoto

_LOGGER = logging.getLogger(__name__)


def require_home_location(hass: HomeAssistant) -> tuple[float, float]:
    """Return (lon, lat) from hass.config, or raise if home location is unset.

    HomeAssistant's own core default for an unconfigured home location is
    exactly 0.0/0.0 (homeassistant.core_config.Config.latitude/longitude
    default to `0`), not None - so a never-configured HA instance produces a
    plausible-looking but bogus GoTo request instead of an obvious error
    unless we check for it explicitly. (0, 0) itself is a real ocean
    location off West Africa, but for a home-astronomy setup treating it as
    "not configured" is by far the safer assumption - this is a physical
    GoTo, not a read-only query.
    """
    lat = hass.config.latitude
    lon = hass.config.longitude
    if lat == 0 and lon == 0:
        raise HomeAssistantError(
            "Bitte zuerst den HA-Heimatort in den Einstellungen konfigurieren"
        )
    return lon, lat


async def async_goto_dso(
    hass: HomeAssistant,
    client: DwarfMiniClient,
    *,
    ra: float,
    dec: float,
    target_name: str,
) -> None:
    """Send a ReqOneClickGotoDSO for (ra, dec) and raise on device rejection.

    shooting_mode=2 and goto_only=False are fixed v1 defaults, mirroring
    button.py's DwarfMiniStartCaptureButton: mode 2 is the astro
    live-stacking shooting mode (matches the capture button's own default
    target), and goto_only=False lets the device run its normal full
    one-click sequence (goto + tracking) rather than stopping short at
    slew-only. Not exposed as parameters: v1 has no shooting-mode-selection
    UI/service field.
    """
    lon, lat = require_home_location(hass)
    request = ReqOneClickGotoDSO(
        ra=ra,
        dec=dec,
        target_name=target_name,
        lon=lon,
        lat=lat,
        shooting_mode=2,
        goto_only=False,
    )
    _LOGGER.debug(
        "Sending GoTo request for %s (module=%s cmd=%s)",
        target_name, MODULE_ASTRO, CMD_ASTRO_START_ONE_CLICK_GOTO_DSO,
    )
    response = await client.send_request(
        MODULE_ASTRO, CMD_ASTRO_START_ONE_CLICK_GOTO_DSO, request, ResOneClickGoto
    )
    if response.code != 0:
        _LOGGER.warning(
            "DWARF mini rejected GoTo to %s (code=%s)", target_name, response.code
        )
        raise HomeAssistantError(
            f"DWARF mini rejected GoTo to {target_name} (code={response.code})"
        )
