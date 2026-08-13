# custom_components/dwarf_mini/__init__.py
"""The DWARF mini integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import DwarfMiniClient
from .const import CONF_HOST, CONF_PORT

# button doesn't exist yet (Task 10 creates it). That task should append its
# platform name here once its module lands - the forwarding/unloading calls
# below are already unconditional and only need this list to be non-empty to
# take effect. Each platform's async_setup_entry receives the same
# `entry: DwarfMiniConfigEntry` and reads the client via `entry.runtime_data`
# (see below) - no hass.data lookup needed.
PLATFORMS: list[str] = ["binary_sensor", "sensor"]

# Plain assignment (not a PEP 695 `type` statement) to match this codebase's
# existing `from __future__ import annotations` + plain-alias conventions.
DwarfMiniConfigEntry = ConfigEntry[DwarfMiniClient]


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
