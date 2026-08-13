"""Binary sensor platform for DWARF mini."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DwarfMiniConfigEntry
from .client import DwarfMiniClient
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DwarfMiniConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client: DwarfMiniClient = entry.runtime_data
    async_add_entities([DwarfMiniConnectedSensor(client, entry)])


class DwarfMiniConnectedSensor(BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_has_entity_name = True
    _attr_translation_key = "connected"
    _attr_should_poll = False

    def __init__(self, client: DwarfMiniClient, entry: DwarfMiniConfigEntry) -> None:
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_connected"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name="DWARF mini"
        )

    @property
    def is_on(self) -> bool:
        return self._client.connected

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._client.add_listener(self.async_write_ha_state))
