"""Fixtures for tests inside the actual Home Assistant runtime on Linux."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def custom_integration(enable_custom_integrations):
    """Allow loading our standalone HACS integration."""
    yield


@pytest.fixture
def login():
    """Fake only the remote authorization server."""
    with patch("custom_components.connectsmarthome.config_flow.LoginControl") as cls:
        instance = cls.return_value
        instance.qr_code.return_value = {
            "success": True,
            "result": {"qrcode": "fake-qr"},
        }
        instance.login_result.return_value = (
            True,
            {
                "uid": "fake-user",
                "t": 123,
                "expire_time": 7200,
                "access_token": "fake-access",
                "refresh_token": "fake-refresh",
                "endpoint": "https://example.invalid",
                "terminal_id": "fake-terminal",
            },
        )
        yield instance


@pytest.fixture(autouse=True)
def setup_entry():
    """Flow tests must not open real cloud or MQTT connections after setup."""
    with patch(
        "custom_components.connectsmarthome.async_setup_entry", return_value=True
    ):
        yield
