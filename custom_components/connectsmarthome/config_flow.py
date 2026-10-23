"""ConnectSmartHome QR flow, adapted from Home Assistant Tuya; see NOTICE."""

from collections.abc import Mapping
from typing import Any

import probatio
import requests
from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector
from tuya_sharing import LoginControl

from .const import (
    CONF_ENDPOINT,
    CONF_TERMINAL_ID,
    CONF_TOKEN_INFO,
    CONF_USER_CODE,
    DOMAIN,
    TUYA_CLIENT_ID,
    TUYA_SCHEMA,
)

TOKEN_FIELDS = ("t", "uid", "expire_time", "access_token", "refresh_token")


class ConnectSmartHomeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Authorize an account using the ConnectSmartHome app."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize an independent authorization session per flow."""
        self._login = LoginControl()
        self._user_code = ""
        self._qr_code: str | None = None

    async def _request_qr(self, user_code: str) -> tuple[str | None, dict[str, str]]:
        """Request a QR token without logging account credentials."""
        self._qr_code = None
        self._user_code = user_code.strip()
        try:
            response = await self.hass.async_add_executor_job(
                self._login.qr_code, TUYA_CLIENT_ID, TUYA_SCHEMA, self._user_code
            )
        except requests.RequestException:
            return "cannot_connect", {}
        except ValueError, TypeError:
            return "invalid_response", {}
        if not isinstance(response, dict):
            return "invalid_response", {}
        if not response.get("success"):
            return "login_error", {
                "code": str(response.get("code", "unknown")),
                "msg": str(response.get("msg", "Request rejected")),
            }
        result = response.get("result")
        token = result.get("qrcode") if isinstance(result, dict) else None
        if not isinstance(token, str) or not token:
            return "invalid_response", {}
        self._qr_code = token
        return None, {}

    async def _user_form(
        self, step: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Share initial and reauthentication User Code validation."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            error, placeholders = await self._request_qr(user_input[CONF_USER_CODE])
            if error is None:
                return await self.async_step_scan()
            errors["base"] = error
        return self.async_show_form(
            step_id=step,
            data_schema=probatio.Schema(
                {probatio.Required(CONF_USER_CODE, default=self._user_code): str}
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the ConnectSmartHome User Code."""
        return await self._user_form("user", user_input)

    def _scan_form(self, error: str | None = None) -> ConfigFlowResult:
        """Keep a pending token until explicitly refreshed."""
        return self.async_show_form(
            step_id="scan",
            data_schema=probatio.Schema(
                {
                    probatio.Optional("QR"): selector.QrCodeSelector(
                        config=selector.QrCodeSelectorConfig(
                            # Tuya's wire protocol is independent of app branding.
                            data=f"tuyaSmart--qrLogin?token={self._qr_code}",
                            scale=5,
                            error_correction_level=selector.QrErrorCorrectionLevel.QUARTILE,
                        )
                    ),
                    probatio.Optional("refresh_qr", default=False): bool,
                }
            ),
            errors={"base": error} if error else {},
        )

    async def async_step_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm phone approval and persist the authorized session."""
        if self._qr_code is None or (user_input and user_input.get("refresh_qr")):
            error, placeholders = await self._request_qr(self._user_code)
            if error:
                return self.async_show_form(
                    step_id="reauth_user_code"
                    if self.source == SOURCE_REAUTH
                    else "user",
                    data_schema=probatio.Schema(
                        {
                            probatio.Required(
                                CONF_USER_CODE, default=self._user_code
                            ): str
                        }
                    ),
                    errors={"base": error},
                    description_placeholders=placeholders,
                )
            return self._scan_form()
        if user_input is None:
            return self._scan_form()
        try:
            success, info = await self.hass.async_add_executor_job(
                self._login.login_result, self._qr_code, TUYA_CLIENT_ID, self._user_code
            )
        except requests.RequestException:
            return self._scan_form("cannot_connect")
        except ValueError, TypeError:
            return self._scan_form("invalid_response")
        if not success:
            # Replacing a pending QR here would invalidate the code on the phone.
            return self._scan_form("not_authorized")
        if not isinstance(info, dict) or any(
            key not in info or info[key] is None or info[key] == ""
            for key in (*TOKEN_FIELDS, CONF_TERMINAL_ID, CONF_ENDPOINT)
        ):
            return self._scan_form("invalid_response")
        if not isinstance(info["uid"], str):
            return self._scan_form("invalid_response")
        entry_data = {
            CONF_USER_CODE: self._user_code,
            CONF_TOKEN_INFO: {key: info[key] for key in TOKEN_FIELDS},
            CONF_TERMINAL_ID: info[CONF_TERMINAL_ID],
            CONF_ENDPOINT: info[CONF_ENDPOINT],
        }
        if self.source == SOURCE_REAUTH:
            entry = self._get_reauth_entry()
            if entry.data[CONF_TOKEN_INFO]["uid"] != info["uid"]:
                return self.async_abort(reason="wrong_account")
            return self.async_update_reload_and_abort(entry, data=entry_data)
        await self.async_set_unique_id(info["uid"])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="ConnectSmartHome", data=entry_data)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Request a new phone approval when authentication expires."""
        self._user_code = entry_data.get(CONF_USER_CODE, "")
        if self._user_code:
            return await self.async_step_reauth_confirm()
        return await self.async_step_reauth_user_code()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Generate the short-lived token when the user is ready."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        error, _ = await self._request_qr(self._user_code)
        if error:
            return await self.async_step_reauth_user_code()
        return self._scan_form()

    async def async_step_reauth_user_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow correction of the User Code during reauthentication."""
        return await self._user_form("reauth_user_code", user_input)
