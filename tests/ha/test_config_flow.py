"""Real HA loader and flow manager tests; remote authorization is mocked."""

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

DOMAIN = "connectsmarthome"

pytestmark = pytest.mark.asyncio


async def start(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"user_code": "fake-code"}
    )
    assert result["step_id"] == "scan"
    return result


async def test_pairing(hass, login):
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].domain == DOMAIN
    assert result["result"].unique_id == "fake-user"
    assert result["data"]["user_code"] == "fake-code"
    await hass.async_block_till_done()


async def test_pending_then_approved(hass, login):
    result = await start(hass)
    login.login_result.return_value = (False, {"code": "pending"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "not_authorized"}
    assert login.qr_code.call_count == 1


async def test_duplicate(hass, login):
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
