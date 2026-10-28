"""Integration contract tests with mocked local HTTP."""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "everlights_v3"
HOST = "bridge.test"
URL = f"http://{HOST}/v1"


@pytest.fixture
def bridge(aioclient_mock):
    aioclient_mock.get(
        URL,
        json={
            "serial": "test-bridge",
            "firmwareVersion": "test-fw",
            "serverReachable": False,
            "rebootCount": 4,
            "mqttOutageMs": 3000,
        },
    )
    aioclient_mock.get(
        URL + "/zones",
        json=[
            {
                "serial": "test-zone",
                "alias": "Front",
                "active": True,
                "rssi": -70,
                "snr": 12,
            }
        ],
    )
    aioclient_mock.get(
        URL + "/zones/test-zone/sequence",
        json={"alias": "Evening", "pattern": ["FF8040"], "effects": []},
    )
    aioclient_mock.get(
        URL + "/sequences",
        json=[
            {
                "id": "test-preset",
                "alias": "Evening",
                "colorMode": "rgb",
                "pattern": ["FF8040"],
                "effects": [],
            }
        ],
    )
    return aioclient_mock


async def setup(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": HOST},
        unique_id="test-bridge",
        options={"show_panel": False, "clock_sync": False},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_flow_success(hass, bridge):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={"host": HOST}
    )
    assert result["type"] == "create_entry"
    assert result["result"].unique_id == "test-bridge"
    await hass.async_block_till_done()


async def test_flow_cannot_connect(hass, aioclient_mock):
    aioclient_mock.get(URL, exc=TimeoutError())
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={"host": HOST}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_flow_duplicate(hass, bridge):
    entry = MockConfigEntry(domain=DOMAIN, data={"host": HOST}, unique_id="test-bridge")
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={"host": HOST}
    )
    assert result["reason"] == "already_configured"


async def test_setup_services(hass, bridge):
    entry = await setup(hass)
    light = entry.runtime_data.lights["test-zone"]
    assert hass.states.get(light.entity_id).state == "on"
    assert any(s.domain == "sensor" for s in hass.states.async_all())
    assert any(s.domain == "binary_sensor" for s in hass.states.async_all())
    bridge.post(URL + "/zones/test-zone/sequence", status=200)
    await hass.services.async_call(
        DOMAIN,
        "set_pattern",
        {
            "entity_id": light.entity_id,
            "colors": ["#FF8040"],
            "brightness": 128,
            "effects": [{"type": "fade", "value": 999}],
        },
        blocking=True,
    )
    post = next(r for r in reversed(bridge.mock_calls) if r[0] == "POST")
    assert post[2] == {
        "alias": "Home Assistant",
        "colorMode": "rgb",
        "pattern": ["804020"],
        "effects": [{"effectType": "fade", "value": 255}],
    }
    bridge.delete(URL + "/zones/test-zone/sequence", status=204)
    await hass.services.async_call(
        "light", "turn_off", {"entity_id": light.entity_id}, blocking=True
    )
    assert bridge.mock_calls[-1][0] == "DELETE"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_brightness_and_playlist(hass, bridge):
    entry = await setup(hass)
    light = entry.runtime_data.lights["test-zone"]
    bridge.post(URL + "/zones/test-zone/sequence", status=200)
    await light.async_set_pattern(["FF8040"], brightness=255)
    await light.async_turn_on(brightness=50)
    await light.async_turn_on(brightness=255)
    assert bridge.mock_calls[-1][2]["pattern"] == ["FF8040"]
    await light.async_start_playlist(["Evening"], interval=5)
    await hass.async_block_till_done()
    assert light.playlist["running"]
    await light.async_start_playlist(["Evening"], interval=6)
    await hass.async_block_till_done()
    assert light.playlist["running"]
    assert hass.states.get("switch.front_playlist").state == "on"
    await light.async_set_pattern(["FF9A3C"])
    await hass.async_block_till_done()
    assert not light.playlist["running"]
    assert hass.states.get("switch.front_playlist").state == "off"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_presets_and_clock(hass, bridge):
    from homeassistant.exceptions import ServiceValidationError

    entry = await setup(hass)
    light = entry.runtime_data.lights["test-zone"]
    bridge.post(URL + "/sequences", status=201)
    await light.async_save_preset("New", ["FF9A3C"], [{"type": "bars", "value": 400}])
    call = next(c for c in reversed(bridge.mock_calls) if c[0] == "POST")
    assert call[2]["groups"] == ["Home Assistant"]
    assert call[2]["effects"] == [{"effectType": "bars", "value": 255}]
    bridge.put(URL + "/sequences/test-preset", status=200)
    await light.async_save_preset("Evening", ["FF0000"])
    assert any(
        c[0] == "PUT" and str(c[1]).endswith("/test-preset") for c in bridge.mock_calls
    )
    entry.runtime_data.data["presets"].append(
        {"id": "00000000-factory", "alias": "Factory", "colorMode": "none"}
    )
    with pytest.raises(ServiceValidationError):
        await light.async_delete_preset("Factory")
    bridge.delete(URL + "/sequences/test-preset", status=204)
    await light.async_delete_preset("Evening")
    bridge.put(URL + "/time", status=200)
    await hass.services.async_call(DOMAIN, "set_time", {}, blocking=True)
    assert bridge.mock_calls[-1][2]["time"].endswith("Z")
    await hass.config_entries.async_unload(entry.entry_id)


async def test_options(hass, bridge):
    entry = await setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"scan_interval": 30, "clock_sync": False, "show_panel": False},
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.runtime_data.update_interval.total_seconds() == 30
    await hass.config_entries.async_unload(entry.entry_id)


async def test_websockets_and_diagnostics(hass, bridge, hass_ws_client):
    from custom_components.everlights_v3.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    entry = await setup(hass)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "everlights_v3/zones"})
    response = await client.receive_json()
    assert response["result"][0]["entity_id"] == "light.front"
    await client.send_json(
        {"id": 2, "type": "everlights_v3/presets", "entry_id": entry.entry_id}
    )
    response = await client.receive_json()
    assert response["result"][0]["alias"] == "Evening"
    assert response["result"][0]["builtin"] is False
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["entry"]["host"] == "**REDACTED**"
    assert diagnostics["bridge"]["serial"] == "**REDACTED**"
    assert diagnostics["zones"][0]["serial"] == "**REDACTED**"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_panel_lifecycle(hass, bridge):
    from unittest.mock import AsyncMock, patch

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": HOST},
        unique_id="test-bridge",
        options={"clock_sync": False},
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.everlights_v3.panel_custom.async_register_panel",
            new_callable=AsyncMock,
        ) as register,
        patch(
            "custom_components.everlights_v3.ha_frontend.async_remove_panel"
        ) as remove,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert register.call_count == 1
        assert register.call_args.kwargs["require_admin"] is True
        assert await hass.config_entries.async_unload(entry.entry_id)
        remove.assert_called_once_with(hass, "everlights")


async def test_clock_schedule_and_retry(hass, bridge, freezer):
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    bridge.put(URL + "/time", status=200)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": HOST},
        unique_id="test-bridge",
        options={"show_panel": False},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    clock_calls = lambda: len(
        [c for c in bridge.mock_calls if c[0] == "PUT" and str(c[1]).endswith("/time")]
    )
    assert clock_calls() == 1
    freezer.move_to(dt_util.utcnow() + timedelta(hours=6, seconds=1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert clock_calls() == 2
    await hass.config_entries.async_unload(entry.entry_id)


async def test_first_failure_retries(hass, aioclient_mock):
    from homeassistant.config_entries import ConfigEntryState

    aioclient_mock.get(URL, exc=TimeoutError())
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": HOST},
        unique_id="test-bridge",
        options={"show_panel": False, "clock_sync": False},
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
