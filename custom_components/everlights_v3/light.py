"""RGB zone lights and entity services."""

from __future__ import annotations

import asyncio
import random
from urllib.parse import quote
from uuid import uuid4

from homeassistant.components.light import ColorMode, LightEntity, LightEntityFeature
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .api import ApiError
from .const import LOGGER
from .entity import ZoneEntity
from .pattern import (
    EFFECT_TYPES,
    build_sequence,
    is_builtin,
    pattern_brightness,
    scale_pattern,
)


class PatternData(ExtraStoredData):
    def __init__(self, data):
        self.data = data

    def as_dict(self):
        return self.data


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    lights = [ZoneLight(coordinator, serial) for serial in coordinator.data["zones"]]
    coordinator.lights.update({light.serial: light for light in lights})
    async_add_entities(lights)


class ZoneLight(ZoneEntity, LightEntity, RestoreEntity):
    _attr_name = None
    _attr_color_mode = ColorMode.RGB
    _attr_supported_features = LightEntityFeature.EFFECT

    def __init__(self, coordinator, serial):
        super().__init__(coordinator, serial)
        self._attr_unique_id = f"{serial}_light"
        self._attr_supported_color_modes = {ColorMode.RGB}
        self.base = []
        self.last_sequence = {}
        self._brightness = None
        self._observed_data = None
        self.playlist = {
            "running": False,
            "presets": [],
            "interval": 60,
            "shuffle": False,
        }
        self.playlist_task = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if stored := await self.async_get_last_extra_data():
            data = stored.as_dict()
            self.base = data.get("base", [])
            self.last_sequence = data.get("sequence", {})
            self._brightness = data.get("brightness")
        self._remember()

    def _remember(self):
        if self._observed_data is self.coordinator.data:
            return
        self._observed_data = self.coordinator.data
        seq = self.zone.get("sequence") or {}
        pattern = seq.get("pattern") or []
        if pattern and pattern != self.last_sequence.get("pattern"):
            brightness = pattern_brightness(pattern)
            self.base = (
                [
                    "".join(
                        f"{min(255, round(int(c[i : i + 2], 16) * 255 / brightness)):02X}"
                        for i in (0, 2, 4)
                    )
                    for c in pattern
                ]
                if brightness
                else pattern[:]
            )
            self._brightness = brightness
            self.last_sequence = seq.copy()

    def _handle_coordinator_update(self):
        self._remember()
        super()._handle_coordinator_update()

    @property
    def extra_restore_state_data(self):
        return PatternData(
            {
                "base": self.base,
                "sequence": self.last_sequence,
                "brightness": self._brightness,
            }
        )

    @property
    def is_on(self):
        return bool(self.zone.get("active") and self.zone.get("sequence"))

    @property
    def brightness(self):
        return (
            self._brightness
            if self._brightness is not None
            else pattern_brightness(
                (self.zone.get("sequence") or {}).get("pattern", [])
            )
        )

    @property
    def rgb_color(self):
        pattern = (
            (self.zone.get("sequence") or {}).get("pattern") or self.base or ["FF9A3C"]
        )
        return tuple(int(pattern[0][i : i + 2], 16) for i in (0, 2, 4))

    @property
    def effect_list(self):
        return list(
            dict.fromkeys(
                p.get("alias", "")
                for p in self.coordinator.data["presets"]
                if p.get("alias")
            )
        ) + [f"Effect: {t}" for t in EFFECT_TYPES]

    @property
    def effect(self):
        alias = (self.zone.get("sequence") or {}).get("alias")
        return (
            alias
            if alias in {p.get("alias") for p in self.coordinator.data["presets"]}
            else None
        )

    @property
    def extra_state_attributes(self):
        seq = self.zone.get("sequence") or {}
        return {k: seq.get(k) for k in ("pattern", "effects", "alias")}

    def preset(self, preset):
        found = next(
            (
                p
                for p in self.coordinator.data["presets"]
                if preset in (p.get("id"), p.get("alias"))
            ),
            None,
        )
        if found is None:
            raise ServiceValidationError(f"Unknown preset: {preset}")
        return found

    async def _send(self, body):
        body["colorMode"] = "rgb"
        await self.coordinator.api.sequence(self.serial, body)
        self.last_sequence = body.copy()

        self.coordinator.delayed_refresh()
        self.async_write_ha_state()

    async def async_set_pattern(
        self, colors, effects=None, brightness=255, alias="Home Assistant"
    ):
        self.stop_playlist()
        try:
            body = build_sequence(colors, effects)
        except (ValueError, TypeError) as err:
            raise ServiceValidationError(str(err)) from err
        self.base = body["pattern"][:]
        self._brightness = brightness
        body.update(
            pattern=scale_pattern(self.base, brightness), alias=alias, colorMode="rgb"
        )
        await self._send(body)

    async def async_turn_on(self, **kwargs):
        self.stop_playlist()
        effect = kwargs.get("effect")
        if effect and not effect.startswith("Effect: "):
            await self.async_play_preset(effect)
            if "brightness" not in kwargs:
                return
        body = self.last_sequence.copy() or {"effects": [], "alias": "Home Assistant"}
        if "rgb_color" in kwargs:
            self.base = build_sequence([kwargs["rgb_color"]])["pattern"]
        if not self.base:
            self.base = ["FF9A3C"]
        if effect and effect.startswith("Effect: "):
            kind = effect.removeprefix("Effect: ")
            if kind not in EFFECT_TYPES:
                raise ServiceValidationError("Unknown effect")
            body["effects"] = [{"effectType": kind, "value": 128}]
        self._brightness = kwargs.get("brightness", self.brightness)
        body.update(pattern=scale_pattern(self.base, self._brightness), colorMode="rgb")
        await self._send(body)

    async def async_turn_off(self, **kwargs):
        self.stop_playlist()
        await self.coordinator.api.sequence(self.serial)
        self.coordinator.delayed_refresh()

    async def async_play_preset(self, preset, _playlist=False):
        if not _playlist:
            self.stop_playlist()
        saved = self.preset(preset)
        self.base = saved.get("pattern", [])[:]
        self._brightness = 255
        await self._send(
            {
                k: saved.get(k, [] if k in ("pattern", "effects") else "rgb")
                for k in ("alias", "colorMode", "pattern", "effects")
            }
        )

    async def async_save_preset(self, name, colors, effects=None):
        try:
            body = build_sequence(colors, effects)
        except (ValueError, TypeError) as err:
            raise ServiceValidationError(str(err)) from err
        existing = next(
            (
                p
                for p in self.coordinator.data["presets"]
                if p.get("alias") == name and not is_builtin(p)
            ),
            None,
        )
        body.update(
            alias=name,
            groups=["Home Assistant"],
            colorMode="rgb",
            id=existing["id"] if existing else str(uuid4()),
        )
        path = f"/sequences/{quote(body['id'], safe='')}" if existing else "/sequences"
        await self.coordinator.api.write("PUT" if existing else "POST", path, body)
        await self.coordinator.async_request_refresh()

    async def async_delete_preset(self, preset):
        saved = self.preset(preset)
        if is_builtin(saved):
            raise ServiceValidationError("Factory presets cannot be deleted")
        await self.coordinator.api.write(
            "DELETE", f"/sequences/{quote(saved['id'], safe='')}"
        )
        await self.coordinator.async_request_refresh()

    def _notify_playlist(self):
        self.coordinator.async_update_listeners()

    def stop_playlist(self):
        if self.playlist_task:
            self.playlist_task.cancel()
            self.playlist_task = None
        self.playlist["running"] = False
        self._notify_playlist()

    async def async_stop_playlist(self):
        self.stop_playlist()

    async def async_start_playlist(self, presets=None, interval=60, shuffle=False):
        previous = self.playlist_task
        self.stop_playlist()
        if previous:
            await asyncio.gather(previous, return_exceptions=True)
        presets = presets if presets is not None else self.playlist["presets"]
        if not presets:
            raise ServiceValidationError("Choose at least one preset first")
        for preset in presets:
            self.preset(preset)
        self.playlist.update(
            running=True, presets=list(presets), interval=interval, shuffle=shuffle
        )

        async def run():
            try:
                index = 0
                while True:
                    items = self.playlist["presets"]
                    await self.async_play_preset(
                        random.choice(items) if shuffle else items[index % len(items)],
                        _playlist=True,
                    )
                    index += 1
                    await asyncio.sleep(interval)
            except (ApiError, ServiceValidationError):
                LOGGER.warning("Playlist stopped after a playback failure")
            finally:
                self.playlist["running"] = False
                self._notify_playlist()

        self.playlist_task = self.hass.async_create_background_task(
            run(), f"EverLights playlist {self.serial}"
        )
        self._notify_playlist()

    async def async_will_remove_from_hass(self):
        self.stop_playlist()
        await super().async_will_remove_from_hass()
