"""Bridge and zone diagnostics."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import ZoneEntity, bridge_device


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    entities = [
        DiagnosticSensor(c, None, key, name, unit, device_class)
        for key, name, unit, device_class in [
            ("rebootCount", "Reboot count", None, None),
            ("mqttOutageMs", "Cloud outage", "s", SensorDeviceClass.DURATION),
            ("firmwareVersion", "Firmware", None, None),
        ]
    ]
    for serial in c.data["zones"]:
        entities.extend(
            DiagnosticSensor(c, serial, key, name, unit, device_class)
            for key, name, unit, device_class in [
                ("rssi", "RSSI", "dBm", SensorDeviceClass.SIGNAL_STRENGTH),
                ("snr", "SNR", "dB", None),
                ("rebootCount", "Reboot count", None, None),
            ]
        )
    async_add_entities(entities)


class DiagnosticSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, serial, key, name, unit, device_class):
        super().__init__(coordinator)
        self.serial, self.key = serial, key
        self._attr_unique_id = f"{serial or coordinator.data['bridge']['serial']}_{key}"
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_entity_registry_enabled_default = key not in ("snr", "rebootCount")
        self._attr_device_info = (
            ZoneEntity(coordinator, serial).device_info
            if serial
            else bridge_device(coordinator)
        )
        if unit:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        data = (
            self.coordinator.data["zones"].get(self.serial, {})
            if self.serial
            else self.coordinator.data["bridge"]
        )
        value = data.get(self.key)
        return (
            value / 1000 if self.key == "mqttOutageMs" and value is not None else value
        )
