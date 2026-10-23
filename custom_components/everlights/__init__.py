"""Custom integration to integrate everlights with Home Assistant.

For more details about this integration, please refer to
https://github.com/theOrakle/everlightsv3
"""
from __future__ import annotations

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EverlightsApiClient
from .coordinator import EverlightsConfigEntry, EverlightsDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.SENSOR,
]


# https://developers.home-assistant.io/docs/config_entries_index/#setting-up-an-entry
async def async_setup_entry(hass: HomeAssistant, entry: EverlightsConfigEntry) -> bool:
    """Set up this integration using UI."""
    host = entry.data[CONF_HOST]
    if entry.unique_id is None:
        # Entries created before the bridge host became the unique ID.
        hass.config_entries.async_update_entry(entry, unique_id=host.lower())

    coordinator = EverlightsDataUpdateCoordinator(
        hass,
        entry,
        EverlightsApiClient(
            host=host,
            session=async_get_clientsession(hass),
        ),
    )
    # Raises ConfigEntryNotReady (retry) or ConfigEntryAuthFailed (reauth).
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EverlightsConfigEntry) -> bool:
    """Handle removal of an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
