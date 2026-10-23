"""EverlightsEntity class."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EverlightsDataUpdateCoordinator


class EverlightsEntity(CoordinatorEntity[EverlightsDataUpdateCoordinator]):
    """Base class for Everlights entities (one device per zone serial)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EverlightsDataUpdateCoordinator,
        entity_description: EntityDescription,
        serial: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self.serial = serial
        self._attr_unique_id = f"{DOMAIN}_{serial}_{entity_description.key}"
        zone_data: dict[str, Any] = coordinator.data.get(serial, {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=serial,
            manufacturer="Everlights",
            model="Controller",
            sw_version=zone_data.get("firmwareVersion"),
            hw_version=str(v) if (v := zone_data.get("hardwareVersion")) is not None else None,
        )
