"""Sensor platform for DWARF mini."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
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
    async_add_entities(
        [
            DwarfMiniBatterySensor(client, entry),
            DwarfMiniCaptureStateSensor(client, entry),
        ]
    )


class _DwarfMiniBaseSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self, client: DwarfMiniClient, entry: DwarfMiniConfigEntry, key: str
    ) -> None:
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name="DWARF mini"
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._client.add_listener(self.async_write_ha_state))


class DwarfMiniBatterySensor(_DwarfMiniBaseSensor):
    _attr_translation_key = "battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, client: DwarfMiniClient, entry: DwarfMiniConfigEntry) -> None:
        super().__init__(client, entry, "battery")

    @property
    def native_value(self) -> int | None:
        return self._client.state.get("battery_percent")


class DwarfMiniCaptureStateSensor(_DwarfMiniBaseSensor):
    _attr_translation_key = "capture_state"
    _attr_device_class = SensorDeviceClass.ENUM
    # Deliberately just the OPERATION_STATE_NAMES values, not the client's
    # "unrecognized" fallback: an unrecognized device value should surface as
    # an invalid/out-of-range state (HA logs it rather than passing it
    # through silently) instead of being quietly accepted as a normal option.
    _attr_options = ["idle", "running", "stopping", "stopped"]

    def __init__(self, client: DwarfMiniClient, entry: DwarfMiniConfigEntry) -> None:
        super().__init__(client, entry, "capture_state")

    @property
    def native_value(self) -> str | None:
        return self._client.state.get("capture_state")

    @property
    def extra_state_attributes(self) -> dict:
        state = self._client.state
        return {
            "progress_current": state.get("progress_current"),
            "progress_total": state.get("progress_total"),
            "progress_stacked": state.get("progress_stacked"),
        }
