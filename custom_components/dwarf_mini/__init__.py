# custom_components/dwarf_mini/__init__.py
"""The DWARF mini integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .client import DwarfMiniClient
from .const import (
    ATTR_DEC_DEGREES,
    ATTR_RA_HOURS,
    ATTR_TARGET_NAME,
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
    SERVICE_GOTO_COORDINATES,
)
from .goto import async_goto_dso

# Config-entry-only integration (config_flow: true in manifest.json, no YAML
# setup) - same CONFIG_SCHEMA guardian uses for the same reason: it makes an
# accidental `dwarf_mini:` section in configuration.yaml fail loudly instead
# of being silently ignored.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# The full v1 platform list. Each platform's async_setup_entry receives the
# same `entry: DwarfMiniConfigEntry` and reads the client via
# `entry.runtime_data` (see below) - no hass.data lookup needed.
PLATFORMS: list[str] = ["binary_sensor", "button", "camera", "select", "sensor"]

# Plain assignment (not a PEP 695 `type` statement) to match this codebase's
# existing `from __future__ import annotations` + plain-alias conventions.
DwarfMiniConfigEntry = ConfigEntry[DwarfMiniClient]

SERVICE_GOTO_COORDINATES_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_RA_HOURS): vol.Coerce(float),
        vol.Required(ATTR_DEC_DEGREES): vol.Coerce(float),
        vol.Optional(ATTR_TARGET_NAME): cv.string,
    }
)


def _client_for_device_id(hass: HomeAssistant, device_id: str) -> DwarfMiniClient:
    """Resolve a device_id (from a service call) to its DwarfMiniClient.

    Registered once in async_setup (not per config entry - see
    async_setup below), so a service call must itself say which of
    potentially several configured DWARF mini devices it targets, the same
    way core integrations like `guardian` do it.
    """
    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get(device_id)
    if device_entry is None:
        raise HomeAssistantError(f"Unknown device_id: {device_id}")
    for entry_id in device_entry.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            continue
        try:
            return entry.runtime_data
        except AttributeError as err:
            # entry.runtime_data is deleted by HA itself (object.__delattr__)
            # the moment async_unload_entry returns True - see
            # homeassistant.config_entries.ConfigEntry.async_unload. This
            # service is registered once in async_setup and never torn down
            # per entry, so it stays callable across an entry's whole
            # lifecycle, including while that entry is unloaded (a normal
            # integration "reload" unloads-then-reloads; the entry can also
            # simply be disabled and left unloaded). A call landing in that
            # window must not surface the raw AttributeError to the caller.
            raise HomeAssistantError(
                f"DWARF mini device_id {device_id} is not currently loaded"
            ) from err
    raise HomeAssistantError(f"No DWARF mini config entry for device_id: {device_id}")


async def _async_handle_goto_coordinates(call: ServiceCall) -> None:
    """Handle dwarf_mini.goto_coordinates: free-coordinate GoTo for
    automations/scripts that want an arbitrary RA/Dec not in the
    select.dwarf_mini_goto_target catalog (design doc section 3). Reuses the
    exact same verified request path as select.py's DSO branch - see
    goto.py.
    """
    client = _client_for_device_id(call.hass, call.data[ATTR_DEVICE_ID])
    ra = call.data[ATTR_RA_HOURS]
    dec = call.data[ATTR_DEC_DEGREES]
    target_name = call.data.get(ATTR_TARGET_NAME) or f"RA {ra}h Dec {dec}\N{DEGREE SIGN}"
    await async_goto_dso(call.hass, client, ra=ra, dec=dec, target_name=target_name)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the DWARF mini integration - register domain-wide services.

    Called once at HA startup (or when the first config entry for this
    domain is set up), independent of how many config entries exist - the
    correct place for a domain-level, device-targeted service, matching how
    core integrations like `guardian` register theirs (async_setup, not
    async_setup_entry). No has_service guard needed here since this runs
    exactly once regardless of config entry count, and no per-entry
    unregister is needed either: the handler resolves the right client
    per-call via device_id (see _client_for_device_id above), so the
    service's own lifecycle is independent of any single entry's.
    """
    hass.services.async_register(
        DOMAIN,
        SERVICE_GOTO_COORDINATES,
        _async_handle_goto_coordinates,
        schema=SERVICE_GOTO_COORDINATES_SCHEMA,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: DwarfMiniConfigEntry) -> bool:
    """Set up DWARF mini from a config entry."""
    session = async_get_clientsession(hass)
    client = DwarfMiniClient(
        session=session,
        ws_url=f"ws://{entry.data[CONF_HOST]}:{entry.data[CONF_PORT]}/",
    )
    # Stored on the entry itself (the modern/idiomatic HA pattern) rather than
    # hass.data[DOMAIN][entry_id]: HA automatically deletes this attribute
    # once async_unload_entry returns True (see ConfigEntry.async_unload),
    # so there's no manual dict bookkeeping to get wrong.
    entry.runtime_data = client

    # NOTE: we don't await an initial client.connect() / probe here before
    # returning True, so a device that's unreachable at startup does not
    # raise ConfigEntryNotReady - run_forever()'s own backoff loop (started
    # below) keeps retrying the connection indefinitely on its own, and
    # connectivity-dependent entities (Task 8's binary_sensor) are expected
    # to reflect `client.connected` rather than assume connected-at-setup.
    entry.async_create_background_task(
        hass, client.run_forever(), name=f"dwarf_mini-{entry.entry_id}"
    )

    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DwarfMiniConfigEntry) -> bool:
    """Unload a DWARF mini config entry."""
    unloaded = True
    if PLATFORMS:
        unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unloaded:
        # entry.runtime_data is guaranteed set here: it's assigned unconditionally
        # in async_setup_entry above and HA only calls async_unload_entry for an
        # entry that previously finished async_setup_entry successfully.
        await entry.runtime_data.close()

    return unloaded
