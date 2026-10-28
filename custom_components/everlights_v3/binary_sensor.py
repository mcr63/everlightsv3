"""Bridge connectivity diagnostics."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import bridge_device


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([CloudReachable(entry.runtime_data)])


class CloudReachable(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Cloud reachable"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data['bridge']['serial']}_cloud"
        self._attr_device_info = bridge_device(coordinator)

    @property
    def is_on(self):
        return self.coordinator.data["bridge"].get("serverReachable", False)
