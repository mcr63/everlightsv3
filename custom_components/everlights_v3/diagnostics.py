"""Redacted integration diagnostics."""

from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data


async def async_get_config_entry_diagnostics(hass, entry):
    data = entry.runtime_data.data
    # Zone serials also appear as mapping keys; export values instead.
    return async_redact_data(
        {
            "entry": {"host": entry.data["host"]},
            "bridge": data["bridge"],
            "zones": list(data["zones"].values()),
            "presets": data["presets"],
        },
        {
            "serial",
            "mac",
            "accountId",
            "host",
            "zoneSerials",
            "macAddress",
            "localIp",
            "ssid",
            "network",
        },
    )
