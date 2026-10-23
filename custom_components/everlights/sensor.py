"""Sensor platform for everlights."""
from __future__ import annotations

from datetime import datetime as dt
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorDeviceClass
from homeassistant.const import EntityCategory

from .const import LOGGER
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EverlightsConfigEntry, EverlightsDataUpdateCoordinator
from .entity import EverlightsEntity

ENTITY_DESCRIPTIONS = (
    SensorEntityDescription(
        key="rssi",
        name="Signal Strength",
        icon="mdi:signal-variant",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement="dBm",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="snr",
        name="Signal to Noise",
        icon="mdi:sine-wave",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement="dB",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="lastRequestDate",
        name="Last Request Date",
        icon="mdi:timeline-clock-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="lastResponseDate",
        name="Last Response Time",
        icon="mdi:timeline-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EverlightsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = entry.runtime_data
    async_add_entities(
        EverlightsSensor(
            coordinator=coordinator,
            entity_description=entity_description,
            serial=serial
        )
        for entity_description in ENTITY_DESCRIPTIONS
        for serial in coordinator.data
    )


class EverlightsSensor(EverlightsEntity, SensorEntity):
    """everlights Sensor class."""

    def __init__(
        self,
        coordinator: EverlightsDataUpdateCoordinator,
        entity_description: SensorEntityDescription,
        serial: str,
    ) -> None:
        """Initialize the sensor class."""
        super().__init__(coordinator,entity_description,serial)

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        desc = self.entity_description
        value = self.coordinator.data.get(self.serial, {}).get(desc.key)
        if desc.device_class == SensorDeviceClass.TIMESTAMP:
            if not value:
                return None
            try:
                # Bridge returns UTC with trailing Z; fromisoformat expects +00:00.
                return dt.fromisoformat(value.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                LOGGER.warning(
                    "Invalid timestamp for %s (%s): %s",
                    self.serial,
                    desc.key,
                    value,
                )
                return None
        return value
