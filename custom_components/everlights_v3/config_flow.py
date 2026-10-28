"""Bridge discovery and options."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ApiError, BridgeApi
from .const import DOMAIN


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            host = user_input["host"].strip()
            try:
                info = await BridgeApi(
                    host, async_get_clientsession(self.hass)
                ).request("GET")
                serial = str(info["serial"])
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"EverLights {serial}", data={"host": host}
                )
            except ApiError:
                errors["base"] = "cannot_connect"
            except (KeyError, TypeError, ValueError):
                errors["base"] = "unknown"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("host"): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()


class OptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        entry = self.hass.config_entries.async_get_entry(self.handler)
        opts = entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "scan_interval", default=opts.get("scan_interval", 10)
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                    vol.Required(
                        "clock_sync", default=opts.get("clock_sync", True)
                    ): bool,
                    vol.Required(
                        "show_panel", default=opts.get("show_panel", True)
                    ): bool,
                }
            ),
        )
