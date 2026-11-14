"""Setup when the middleware is not reachable yet.

Regression cover for 2026-11-14: after a Proxmox host reboot, Home Assistant
set the integration up before the Guardian add-on was listening. The session
check failed with a DNS timeout, was read as "session expired", and a reauth
flow was started even though the stored session was still valid.

An unreachable middleware must make setup retry (ConfigEntryNotReady); only a
middleware that answers and rejects the session may lead to re-authentication.
"""
import asyncio
from unittest.mock import MagicMock

import aiohttp
import pytest
from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.intelbras_guardian import async_setup_entry
from custom_components.intelbras_guardian.api_client import (
    GuardianApiClient,
    GuardianConnectionError,
)
from custom_components.intelbras_guardian.const import (
    CONF_FASTAPI_HOST,
    CONF_FASTAPI_PORT,
    CONF_SESSION_ID,
)


class _Response:
    def __init__(self, status):
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    """Minimal stand-in for aiohttp.ClientSession.get()."""

    def __init__(self, *, status=None, error=None):
        self._status = status
        self._error = error

    async def get(self, *args, **kwargs):
        if self._error is not None:
            raise self._error
        return _Response(self._status)


def _client(session):
    client = GuardianApiClient(host="addon", port=8000, session=session)
    client.set_session_id("stored-session")
    return client


@pytest.mark.parametrize(
    "error",
    [
        aiohttp.ClientConnectorError(MagicMock(), OSError("Timeout while contacting DNS servers")),
        asyncio.TimeoutError(),
    ],
)
def test_check_session_raises_when_middleware_unreachable(error):
    client = _client(_Session(error=error))

    with pytest.raises(GuardianConnectionError):
        asyncio.run(client.check_session())


def test_check_session_false_when_middleware_rejects_session():
    client = _client(_Session(status=401))

    assert asyncio.run(client.check_session()) is False


def test_check_session_true_when_session_valid():
    client = _client(_Session(status=200))

    assert asyncio.run(client.check_session()) is True


def test_setup_retries_instead_of_reauth_when_middleware_unreachable(monkeypatch):
    error = aiohttp.ClientConnectorError(MagicMock(), OSError("DNS timeout"))
    monkeypatch.setattr(
        "custom_components.intelbras_guardian.async_get_clientsession",
        lambda hass: _Session(error=error),
    )

    hass = MagicMock()
    hass.data = {}
    entry = MagicMock()
    entry.data = {
        CONF_FASTAPI_HOST: "addon",
        CONF_FASTAPI_PORT: 8000,
        CONF_SESSION_ID: "stored-session",
    }
    entry.options = {}

    with pytest.raises(ConfigEntryNotReady):
        asyncio.run(async_setup_entry(hass, entry))

    entry.async_start_reauth.assert_not_called()
