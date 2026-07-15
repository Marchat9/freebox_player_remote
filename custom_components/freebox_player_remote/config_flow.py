"""Config flow for the Freebox Player HID integration."""
from __future__ import annotations

import ipaddress
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .client import (
    CannotConnect,
    ConnectionRefused,
    ConnectionTimeout,
    InvalidHost,
    async_discover_port,
    test_connection,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
    }
)

# Maps client.py's own exception hierarchy directly to config-flow error
# codes (see strings.json/translations). No local exception hierarchy is
# needed to mirror it -- these are the only exceptions test_connection() can
# raise, so we just translate them straight to a UI-facing string.
_ERROR_CODES: dict[type[Exception], str] = {
    InvalidHost: "invalid_host",
    ConnectionRefused: "connection_refused",
    ConnectionTimeout: "timeout_connect",
    CannotConnect: "cannot_connect",
}


class DiscoveryFailed(HomeAssistantError):
    """No port was provided and mDNS discovery did not find one."""


async def _validate_and_connect(hass: HomeAssistant, host: str, port: int | None) -> int:
    """Validate the host, resolve the port and attempt a real RUDP handshake.

    Returns the port to store in the config entry. Raises a client.py
    exception (mapped via _ERROR_CODES) or DiscoveryFailed on failure --
    never a generic catch-all, so the UI can show a message specific to
    what actually went wrong.
    """
    try:
        ipaddress.IPv4Address(host)
    except ValueError as err:
        raise InvalidHost(str(err)) from err

    if port is None:
        port = await async_discover_port(hass, host)
        if port is None:
            raise DiscoveryFailed

    await hass.async_add_executor_job(test_connection, host, port)
    return port


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Freebox Player HID."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """First (and only) step: ask for host/port and test the connection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT)

            try:
                resolved_port = await _validate_and_connect(self.hass, host, port)
            except DiscoveryFailed:
                errors["base"] = "discovery_failed"
            except tuple(_ERROR_CODES) as err:
                errors["base"] = next(
                    code for exc_type, code in _ERROR_CODES.items() if isinstance(err, exc_type)
                )
            except Exception:  # pragma: no cover - unexpected failure safety net
                _LOGGER.exception(
                    "Unexpected error while testing the Freebox Player HID connection"
                )
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Freebox Player ({host})",
                    data={CONF_HOST: host, CONF_PORT: resolved_port},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
