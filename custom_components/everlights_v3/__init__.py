"""EverLights v3 local integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from inspect import signature
from pathlib import Path

import voluptuous as vol
from homeassistant.auth.permissions.const import POLICY_CONTROL
from homeassistant.components import frontend as ha_frontend
from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import service as service_helper
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import ApiError, BridgeApi
from .const import DOMAIN, LOGGER, PLATFORMS, VERSION
from .coordinator import BridgeCoordinator, EverlightsConfigEntry
from .entity import bridge_device
from .pattern import EFFECT_TYPES, is_builtin

EFFECT_SCHEMA = vol.Schema(
    {
        vol.Required("type"): vol.In(EFFECT_TYPES),
        vol.Optional("value", default=128): vol.All(
            vol.Coerce(int), vol.Clamp(min=0, max=255)
        ),
    }
)
COLORS = vol.All(cv.ensure_list, vol.Length(min=1))


async def sync_clock(coordinator, _now=None):
    try:
        await coordinator.api.write(
            "PUT",
            "/time",
            {"time": dt_util.utcnow().isoformat().replace("+00:00", "Z")},
        )
    except ApiError:
        LOGGER.warning("Could not synchronize bridge clock")


async def async_setup(hass, config):
    hass.data.setdefault(
        DOMAIN,
        {"entries": {}, "panel": False, "static": False, "panel_lock": asyncio.Lock()},
    )
    schemas = {
        "set_pattern": (
            {
                vol.Required("colors"): COLORS,
                vol.Optional("effects", default=[]): [EFFECT_SCHEMA],
                vol.Optional("brightness", default=255): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=255)
                ),
                vol.Optional("alias", default="Home Assistant"): str,
            },
            "async_set_pattern",
        ),
        "play_preset": ({vol.Required("preset"): str}, "async_play_preset"),
        "save_preset": (
            {
                vol.Required("name"): str,
                vol.Required("colors"): COLORS,
                vol.Optional("effects", default=[]): [EFFECT_SCHEMA],
            },
            "async_save_preset",
        ),
        "delete_preset": ({vol.Required("preset"): str}, "async_delete_preset"),
        "start_playlist": (
            {
                vol.Required("presets"): vol.All([str], vol.Length(min=1)),
                vol.Optional("interval", default=60): vol.All(
                    vol.Coerce(float), vol.Range(min=5, max=86400)
                ),
                vol.Optional("shuffle", default=False): bool,
            },
            "async_start_playlist",
        ),
        "stop_playlist": ({}, "async_stop_playlist"),
    }

    def make_handler(method):
        async def handle(call):
            lights = [
                light
                for c in hass.data[DOMAIN]["entries"].values()
                for light in c.lights.values()
            ]
            extract = service_helper.async_extract_entities
            args = (
                (hass, lights, call)
                if "hass" in signature(extract).parameters
                else (lights, call)
            )
            entities = await extract(*args)
            if not entities:
                raise ServiceValidationError("Select an available EverLights v3 light")
            user = (
                await hass.auth.async_get_user(call.context.user_id)
                if call.context.user_id
                else None
            )
            if call.context.user_id and user is None:
                raise Unauthorized(context=call.context)
            for entity in entities:
                if user and not user.permissions.check_entity(
                    entity.entity_id, POLICY_CONTROL
                ):
                    raise Unauthorized(context=call.context, entity_id=entity.entity_id)
            data = {
                key: value
                for key, value in call.data.items()
                if key not in cv.ENTITY_SERVICE_FIELDS
            }
            for entity in entities:
                await getattr(entity, method)(**data)

        return handle

    for service, (schema, method) in schemas.items():
        hass.services.async_register(
            DOMAIN,
            service,
            make_handler(method),
            schema=cv.make_entity_service_schema(schema),
        )

    async def set_time(call):
        for entry_id, coordinator in hass.data[DOMAIN]["entries"].items():
            if call.data.get("config_entry_id", entry_id) == entry_id:
                await sync_clock(coordinator)

    hass.services.async_register(
        DOMAIN,
        "set_time",
        set_time,
        schema=vol.Schema({vol.Optional("config_entry_id"): str}),
    )
    websocket_api.async_register_command(hass, ws_zones)
    websocket_api.async_register_command(hass, ws_presets)
    return True


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/zones"})
@callback
def ws_zones(hass, connection, msg):
    result = []
    for entry_id, coordinator in hass.data[DOMAIN]["entries"].items():
        for serial, zone in coordinator.data["zones"].items():
            light = coordinator.lights.get(serial)
            result.append(
                {
                    "entry_id": entry_id,
                    "bridge_serial": coordinator.data["bridge"]["serial"],
                    "zone_serial": serial,
                    "entity_id": light.entity_id if light else None,
                    "name": zone.get("alias")
                    or zone.get("name")
                    or f"EverLights {serial}",
                    "active": zone.get("active", False),
                    "sequence": zone.get("sequence"),
                    "playlist": dict(light.playlist)
                    if light
                    else {"running": False, "presets": [], "interval": 60},
                }
            )
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/presets", vol.Optional("entry_id"): str}
)
@callback
def ws_presets(hass, connection, msg):
    result = []
    for entry_id, coordinator in hass.data[DOMAIN]["entries"].items():
        if msg.get("entry_id", entry_id) == entry_id:
            for preset in coordinator.data["presets"]:
                result.append(
                    {
                        **{
                            key: preset.get(key)
                            for key in (
                                "id",
                                "alias",
                                "groups",
                                "colorMode",
                                "pattern",
                                "effects",
                            )
                        },
                        "builtin": is_builtin(preset),
                    }
                )
    connection.send_result(msg["id"], result)


async def update_panel(hass):
    async with hass.data[DOMAIN]["panel_lock"]:
        await _update_panel(hass)


async def _update_panel(hass):
    data = hass.data[DOMAIN]
    wanted = any(
        c.entry.options.get("show_panel", True) for c in data["entries"].values()
    )
    if wanted and not data["panel"]:
        if not data["static"]:
            await hass.http.async_register_static_paths(
                [
                    StaticPathConfig(
                        "/everlights_v3_static/everlights-panel.js",
                        str(Path(__file__).parent / "frontend" / "everlights-panel.js"),
                        False,
                    )
                ]
            )
            data["static"] = True
        await panel_custom.async_register_panel(
            hass,
            webcomponent_name="everlights-panel",
            frontend_url_path="everlights",
            module_url=f"/everlights_v3_static/everlights-panel.js?v={VERSION}",
            sidebar_title="EverLights",
            sidebar_icon="mdi:string-lights",
            require_admin=True,
        )
        data["panel"] = True
    elif not wanted and data["panel"]:
        ha_frontend.async_remove_panel(hass, "everlights")
        data["panel"] = False


async def reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass, entry: EverlightsConfigEntry):
    coordinator = BridgeCoordinator(
        hass, entry, BridgeApi(entry.data["host"], async_get_clientsession(hass))
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **bridge_device(coordinator)
    )
    hass.data[DOMAIN]["entries"][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(reload_entry))
    if entry.options.get("clock_sync", True):
        await sync_clock(coordinator)

        async def scheduled_sync(now):
            await sync_clock(coordinator, now)

        entry.async_on_unload(
            async_track_time_interval(hass, scheduled_sync, timedelta(hours=6))
        )
    await update_panel(hass)
    return True


async def async_unload_entry(hass, entry: EverlightsConfigEntry):
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    for cancel in entry.runtime_data.pending_refreshes:
        cancel()
    entry.runtime_data.pending_refreshes.clear()
    hass.data[DOMAIN]["entries"].pop(entry.entry_id, None)
    await update_panel(hass)
    return True
