"""Tests for the Everlights config flow."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.everlights.api import (
    EverlightsApiClientAuthenticationError,
    EverlightsApiClientCommunicationError,
    EverlightsApiClientError,
)
from custom_components.everlights.const import DOMAIN

ERRORS = [
    (EverlightsApiClientAuthenticationError("bad"), "invalid_auth"),
    (EverlightsApiClientCommunicationError("down"), "cannot_connect"),
    (EverlightsApiClientError("boom"), "unknown"),
]


async def test_user_flow_creates_entry(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """A reachable bridge creates an entry whose unique ID is the host."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: " 192.168.1.60 "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "192.168.1.60"
    assert result["data"] == {CONF_HOST: "192.168.1.60"}
    assert result["result"].unique_id == "192.168.1.60"


@pytest.mark.parametrize(("exception", "error"), ERRORS)
async def test_user_flow_errors_recover(
    hass: HomeAssistant, mock_client: MagicMock, exception: Exception, error: str
) -> None:
    """Each failure shows its error and the flow can still finish afterwards."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    mock_client.async_get_data.side_effect = exception
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.60"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_client.async_get_data.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.60"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_duplicate_aborts(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """The same bridge cannot be added twice."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.50"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_updates_host(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Reconfiguring moves the entry (and its unique ID) to the new host."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.99"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_HOST] == "192.168.1.99"
    assert mock_config_entry.unique_id == "192.168.1.99"


async def test_reconfigure_same_host_is_allowed(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Re-submitting the current host is not treated as a duplicate."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.50"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


async def test_reconfigure_to_other_entrys_host_aborts(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Reconfiguring onto a host another entry owns is refused."""
    mock_config_entry.add_to_hass(hass)
    MockConfigEntry(
        domain=DOMAIN, unique_id="192.168.1.77", data={CONF_HOST: "192.168.1.77"}
    ).add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.77"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(("exception", "error"), ERRORS)
async def test_reconfigure_errors_recover(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    exception: Exception,
    error: str,
) -> None:
    """A failed reconfigure shows the error and can be retried."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    mock_client.async_get_data.side_effect = exception
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.99"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_client.async_get_data.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.99"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
