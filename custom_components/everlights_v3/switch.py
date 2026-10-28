"""Playlist control for each zone."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .entity import ZoneEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            PlaylistSwitch(entry.runtime_data, serial)
            for serial in entry.runtime_data.data["zones"]
        ]
    )


class PlaylistSwitch(ZoneEntity, SwitchEntity):
    _attr_name = "Playlist"
    _attr_icon = "mdi:playlist-play"

    def __init__(self, coordinator, serial):
        super().__init__(coordinator, serial)
        self._attr_unique_id = f"{serial}_playlist"

    @property
    def light(self):
        return self.coordinator.lights[self.serial]

    @property
    def is_on(self):
        return (
            self.light.playlist["running"]
            if self.serial in self.coordinator.lights
            else False
        )

    async def async_turn_on(self, **kwargs):
        playlist = self.light.playlist
        await self.light.async_start_playlist(
            playlist["presets"], playlist["interval"], playlist["shuffle"]
        )

    async def async_turn_off(self, **kwargs):
        self.light.stop_playlist()
