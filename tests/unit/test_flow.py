"""Exercise the actual flow on Windows with only HA's UI API adapted.

Network calls use the real SDK interface with mocks; probatio is real.
This does not claim to be a Home Assistant runtime or physical-device test.
"""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "custom_components/connectsmarthome"


@pytest.fixture
def flow(monkeypatch):
    """Load real config_flow.py without importing HA's unsupported Windows runtime."""

    class FlowAPI:
        def __init_subclass__(cls, **kwargs):
            pass

        def async_show_form(self, **kwargs):
            return {"type": "form", **kwargs}

        def async_create_entry(self, **kwargs):
            return {"type": "create_entry", **kwargs}

        def async_abort(self, **kwargs):
            return {"type": "abort", **kwargs}

        async def async_set_unique_id(self, unique_id):
            self.unique_id = unique_id

        def _abort_if_unique_id_configured(self):
            if self.duplicate:
                raise RuntimeError("already_configured")

        def _get_reauth_entry(self):
            return self.entry

        def async_update_reload_and_abort(self, entry, **kwargs):
            return {"type": "abort", "reason": "reauth_successful", **kwargs}

    class QR:
        def __init__(self, config):
            self.config = config

        def __call__(self, value):
            return value

    constants = ModuleType("csh_flow_test.const")
    for key, value in {
        "CONF_ENDPOINT": "endpoint",
        "CONF_TERMINAL_ID": "terminal_id",
        "CONF_TOKEN_INFO": "token_info",
        "CONF_USER_CODE": "user_code",
        "DOMAIN": "connectsmarthome",
        "TUYA_CLIENT_ID": "HA_3y9q4ak7g4ephrvke",
        "TUYA_SCHEMA": "haauthorize",
    }.items():
        setattr(constants, key, value)
    config_entries = ModuleType("homeassistant.config_entries")
    config_entries.SOURCE_REAUTH = "reauth"
    config_entries.ConfigFlow = FlowAPI
    config_entries.ConfigFlowResult = dict
    helpers = ModuleType("homeassistant.helpers")
    helpers.selector = SimpleNamespace(
        QrCodeSelector=QR,
        QrCodeSelectorConfig=dict,
        QrErrorCorrectionLevel=SimpleNamespace(QUARTILE="quartile"),
    )
    for name, module in {
        "homeassistant": ModuleType("homeassistant"),
        "homeassistant.config_entries": config_entries,
        "homeassistant.helpers": helpers,
        "csh_flow_test": ModuleType("csh_flow_test"),
        "csh_flow_test.const": constants,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location(
        "csh_flow_test.config_flow", COMPONENT / "config_flow.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    instance = module.ConnectSmartHomeConfigFlow()
    instance._login = MagicMock()
    instance._login.qr_code.return_value = {
        "success": True,
        "result": {"qrcode": "fake-qr"},
    }
    instance._login.login_result.return_value = (
        True,
        {
            "t": 123,
            "uid": "fake-user",
            "expire_time": 7200,
            "access_token": "fake-access",
            "refresh_token": "fake-refresh",
            "terminal_id": "fake-terminal",
            "endpoint": "https://example.invalid",
        },
    )

    async def execute(fn, *args):
        return fn(*args)

    instance.hass = SimpleNamespace(async_add_executor_job=execute)
    instance.source = "user"
    instance.duplicate = False
    return instance


def run(coro):
    return asyncio.run(coro)


def begin(flow):
    return run(flow.async_step_user({"user_code": "  fake-caseSensitive  "}))


def test_initial_and_success(flow):
    assert run(flow.async_step_user())["step_id"] == "user"
    assert begin(flow)["step_id"] == "scan"
    flow._login.qr_code.assert_called_once_with(
        "HA_3y9q4ak7g4ephrvke", "haauthorize", "fake-caseSensitive"
    )
    result = run(flow.async_step_scan({}))
    assert result["type"] == "create_entry"
    assert flow.unique_id == "fake-user"
    assert result["data"]["token_info"]["refresh_token"] == "fake-refresh"
    assert "fake-qr" not in json.dumps(result)


def test_pending_scan_keeps_token(flow):
    begin(flow)
    flow._login.login_result.return_value = (False, {"code": "pending"})
    assert run(flow.async_step_scan({}))["errors"] == {"base": "not_authorized"}
    assert flow._qr_code == "fake-qr"
    assert flow._login.qr_code.call_count == 1


def test_explicit_refresh(flow):
    begin(flow)
    flow._login.qr_code.return_value = {"success": True, "result": {"qrcode": "fresh"}}
    assert run(flow.async_step_scan({"refresh_qr": True}))["step_id"] == "scan"
    assert flow._qr_code == "fresh"
    flow._login.login_result.assert_not_called()


@pytest.mark.parametrize("exception", [requests.ConnectionError(), requests.Timeout()])
def test_network_failure(flow, exception):
    flow._login.qr_code.side_effect = exception
    assert begin(flow)["errors"] == {"base": "cannot_connect"}
    flow._login.qr_code.side_effect = None
    begin(flow)
    flow._login.login_result.side_effect = exception
    assert run(flow.async_step_scan({}))["errors"] == {"base": "cannot_connect"}


@pytest.mark.parametrize(
    "response",
    [None, {}, {"success": True}, {"success": True, "result": {"qrcode": ""}}],
)
def test_bad_qr_response(flow, response):
    flow._login.qr_code.return_value = response
    assert begin(flow)["type"] == "form"
    assert flow._qr_code is None


def test_api_rejection_preserves_code(flow):
    flow._login.qr_code.return_value = {
        "success": False,
        "code": "OEM_DISABLED",
        "msg": "Not enabled",
    }
    result = begin(flow)
    assert result["errors"] == {"base": "login_error"}
    assert result["description_placeholders"]["code"] == "OEM_DISABLED"


def test_missing_token_fields(flow):
    begin(flow)
    flow._login.login_result.return_value = (True, {"uid": "fake-user"})
    assert run(flow.async_step_scan({}))["errors"] == {"base": "invalid_response"}


def test_duplicate_account(flow):
    begin(flow)
    flow.duplicate = True
    with pytest.raises(RuntimeError, match="already_configured"):
        run(flow.async_step_scan({}))


def test_reauth_late_qr_and_same_account(flow):
    flow.source = "reauth"
    flow.entry = SimpleNamespace(data={"token_info": {"uid": "fake-user"}})
    result = run(flow.async_step_reauth({"user_code": "fake-code"}))
    assert result["step_id"] == "reauth_confirm"
    flow._login.qr_code.assert_not_called()
    assert run(flow.async_step_reauth_confirm({}))["step_id"] == "scan"
    assert run(flow.async_step_scan({}))["reason"] == "reauth_successful"


def test_reauth_wrong_account(flow):
    begin(flow)
    flow.source = "reauth"
    flow.entry = SimpleNamespace(data={"token_info": {"uid": "other-user"}})
    assert run(flow.async_step_scan({}))["reason"] == "wrong_account"


def test_reauth_code_correction(flow):
    flow.source = "reauth"
    assert run(flow.async_step_reauth({}))["step_id"] == "reauth_user_code"
    assert (
        run(flow.async_step_reauth_user_code({"user_code": "fake-code"}))["step_id"]
        == "scan"
    )


def test_failed_refresh_clears_stale_token(flow):
    begin(flow)
    flow._login.qr_code.side_effect = requests.Timeout()
    result = run(flow.async_step_scan({"refresh_qr": True}))
    assert result["step_id"] == "user"
    assert flow._qr_code is None


def test_packaging():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert manifest["domain"] == "connectsmarthome"
    assert manifest["version"] == "0.1.0-beta.1"
    assert len(list((ROOT / "custom_components").iterdir())) == 1
    assert "[%key:" not in (COMPONENT / "translations/en.json").read_text()
    assert '"tuya_discovery_new"' not in (COMPONENT / "const.py").read_text()
    assert '"tuya_entry_update"' not in (COMPONENT / "const.py").read_text()
