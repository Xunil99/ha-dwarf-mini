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
from .const import DOMAIN, OPERATION_STATE_NAMES


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
            DwarfMiniFocusPositionSensor(client, entry),
            DwarfMiniGotoStateSensor(client, entry),
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
    # "unrecognized" fallback string: SensorEntity.state raises ValueError
    # for an ENUM sensor whose native_value isn't in _attr_options, and that
    # exception is only logged by DwarfMiniClient._notify_listeners's
    # generic `except Exception` - it happens *before* anything is written,
    # so it would silently freeze both state and extra_state_attributes at
    # their last valid values instead of surfacing the problem. native_value
    # below filters "unrecognized" (and any other stray value) down to None
    # so a genuinely unmapped device value becomes HA's own "unknown"
    # instead of crashing the state write.
    _attr_options = list(OPERATION_STATE_NAMES.values())

    def __init__(self, client: DwarfMiniClient, entry: DwarfMiniConfigEntry) -> None:
        super().__init__(client, entry, "capture_state")

    @property
    def native_value(self) -> str | None:
        value = self._client.state.get("capture_state")
        return value if value in self._attr_options else None

    @property
    def extra_state_attributes(self) -> dict:
        state = self._client.state
        return {
            "progress_current": state.get("progress_current"),
            "progress_total": state.get("progress_total"),
            "progress_stacked": state.get("progress_stacked"),
        }


class DwarfMiniFocusPositionSensor(_DwarfMiniBaseSensor):
    _attr_translation_key = "focus_position"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, client: DwarfMiniClient, entry: DwarfMiniConfigEntry) -> None:
        super().__init__(client, entry, "focus_position")

    @property
    def native_value(self) -> int | None:
        return self._client.state.get("focus_position")


class DwarfMiniGotoStateSensor(_DwarfMiniBaseSensor):
    _attr_translation_key = "goto_state"
    _attr_device_class = SensorDeviceClass.ENUM
    # Same "unrecognized" filtering as DwarfMiniCaptureStateSensor above
    # (identical value shape: an OPERATION_STATE_NAMES-derived string with
    # an "unrecognized" fallback) and for the same reason - see that
    # sensor's _attr_options comment for the full explanation of why
    # native_value must filter it out rather than pass it through.
    _attr_options = list(OPERATION_STATE_NAMES.values())

    def __init__(self, client: DwarfMiniClient, entry: DwarfMiniConfigEntry) -> None:
        super().__init__(client, entry, "goto_state")

    @property
    def native_value(self) -> str | None:
        value = self._client.state.get("goto_state")
        return value if value in self._attr_options else None

    @property
    def extra_state_attributes(self) -> dict:
        return {"target_name": self._client.state.get("goto_target_name")}
