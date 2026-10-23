"""DataUpdateCoordinator for everlights."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    EverlightsApiClient,
    EverlightsApiClientAuthenticationError,
    EverlightsApiClientError,
)
from .const import DOMAIN, LOGGER

type EverlightsConfigEntry = ConfigEntry[EverlightsDataUpdateCoordinator]


# https://developers.home-assistant.io/docs/integration_fetching_data#coordinated-single-api-poll-for-data-for-all-entities
class EverlightsDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Class to manage fetching data from the API."""

    config_entry: EverlightsConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: EverlightsConfigEntry,
        client: EverlightsApiClient,
    ) -> None:
        """Initialize."""
        self.client = client
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Update data via library."""
        try:
            return await self.client.async_get_data()
        except EverlightsApiClientAuthenticationError as exception:
            raise ConfigEntryAuthFailed(exception) from exception
        except EverlightsApiClientError as exception:
            raise UpdateFailed(exception) from exception
