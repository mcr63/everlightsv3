"""Polling and shared bridge runtime."""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import quote

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError
from .const import DOMAIN, LOGGER


class BridgeCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, api):
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=entry.options.get("scan_interval", 10)),
        )
        self.api = api
        self.entry = entry
        self.lights = {}
        self.pending_refreshes = set()

    async def _async_update_data(self):
        try:
            bridge = await self.api.request("GET")
            zones = await self.api.request("GET", "/zones")
            presets = await self.api.request("GET", "/sequences")
            if (
                not isinstance(bridge, dict)
                or not bridge.get("serial")
                or not isinstance(zones, list)
                or not isinstance(presets, list)
            ):
                raise ApiError("Invalid bridge data")
            result = {}
            for zone in zones:
                serial = zone["serial"]
                sequence = await self.api.request(
                    "GET", f"/zones/{quote(serial, safe='')}/sequence"
                )
                result[serial] = {**zone, "sequence": sequence}
            return {"bridge": bridge, "zones": result, "presets": presets}
        except (ApiError, KeyError, TypeError) as err:
            raise UpdateFailed("Unable to update bridge") from err

    def delayed_refresh(self):
        from homeassistant.helpers.event import async_call_later

        cancel = None

        async def refresh(_now):
            self.pending_refreshes.discard(cancel)
            await self.async_request_refresh()

        cancel = async_call_later(self.hass, 5, refresh)
        self.pending_refreshes.add(cancel)


type EverlightsConfigEntry = ConfigEntry[BridgeCoordinator]
