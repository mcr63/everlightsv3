"""Device metadata shared by entities."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


def bridge_device(coordinator):
    info = coordinator.data["bridge"]
    return {
        "identifiers": {(DOMAIN, str(info["serial"]))},
        "name": "EverLights bridge",
        "manufacturer": "EverLights",
        "model": "v3 bridge",
        "sw_version": str(info.get("firmwareVersion", "")),
    }


class ZoneEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, serial):
        super().__init__(coordinator)
        self.serial = serial
        zone = coordinator.data["zones"][serial]
        self._attr_device_info = {
            "identifiers": {(DOMAIN, serial)},
            "name": zone.get("alias") or zone.get("name") or f"EverLights {serial}",
            "manufacturer": "EverLights",
            "model": "v3 zone",
            "sw_version": str(zone.get("firmwareVersion", "")),
            "via_device": (DOMAIN, str(coordinator.data["bridge"]["serial"])),
        }

    @property
    def zone(self):
        return self.coordinator.data["zones"].get(self.serial, {})

    @property
    def available(self):
        return super().available and self.serial in self.coordinator.data["zones"]
