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
    async_discover_device,
    test_connection,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_HOST): str,
        vol.Optional(CONF_PORT): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
    }
)

# The confirm_* steps have no fields of their own -- they just recap what
# was found/entered and let the user submit to actually create the entry.
_CONFIRM_SCHEMA = vol.Schema({})

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
    """No host/port was provided and mDNS discovery did not find one."""


async def _validate_and_connect(
    hass: HomeAssistant, host: str | None, port: int | None
) -> tuple[str, int]:
    """Resolve the host/port (via mDNS if needed) and attempt a real RUDP handshake.

    Returns the (host, port) pair to store in the config entry. Raises a
    client.py exception (mapped via _ERROR_CODES) or DiscoveryFailed on
    failure -- never a generic catch-all, so the UI can show a message
    specific to what actually went wrong.
    """
    if host is None:
        # Both fields left empty: find any Foils HID device on the network.
        device = await async_discover_device(hass)
        if device is None:
            raise DiscoveryFailed
        host, port = device
    else:
        try:
            ipaddress.IPv4Address(host)
        except ValueError as err:
            raise InvalidHost(str(err)) from err

        if port is None:
            device = await async_discover_device(hass, host)
            if device is None:
                raise DiscoveryFailed
            _, port = device

    await hass.async_add_executor_job(test_connection, host, port)
    return host, port


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Freebox Player HID."""

    VERSION = 1

    def __init__(self) -> None:
        # Filled in by async_step_user once the connection test succeeds;
        # read back by the confirm_* steps to actually create the entry.
        self._resolved_host: str | None = None
        self._resolved_port: int | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """First step: ask for host/port and test the connection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input.get(CONF_HOST)
            port = user_input.get(CONF_PORT)

            try:
                resolved_host, resolved_port = await _validate_and_connect(self.hass, host, port)
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
                # Catch already-configured Freeboxes here, before the confirm
                # screen -- no point recapping a connection we're about to abort.
                await self.async_set_unique_id(resolved_host)
                self._abort_if_unique_id_configured()

                self._resolved_host = resolved_host
                self._resolved_port = resolved_port

                if host is None:
                    return await self.async_step_confirm_auto()
                if port is None:
                    return await self.async_step_confirm_port_auto()
                return await self.async_step_confirm_manual()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def _async_confirm(self, step_id: str, user_input: dict[str, Any] | None) -> FlowResult:
        """Shared recap screen: create the entry once the user submits it."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"Freebox Player ({self._resolved_host}:{self._resolved_port})",
                data={CONF_HOST: self._resolved_host, CONF_PORT: self._resolved_port},
            )

        return self.async_show_form(
            step_id=step_id,
            data_schema=_CONFIRM_SCHEMA,
            description_placeholders={
                "host": self._resolved_host,
                "port": str(self._resolved_port),
            },
        )

    async def async_step_confirm_auto(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Recap step: both host and port were found automatically via mDNS."""
        return await self._async_confirm("confirm_auto", user_input)

    async def async_step_confirm_port_auto(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Recap step: host was given, port was found automatically via mDNS."""
        return await self._async_confirm("confirm_port_auto", user_input)

    async def async_step_confirm_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Recap step: both host and port were entered manually."""
        return await self._async_confirm("confirm_manual", user_input)
