"""The Freebox Player HID integration.

Pilots a Freebox Player's remote control over the network (Foils HID / RUDP
protocol) -- no entity/state, just a `press` service, since the protocol
carries no feedback from the Player.
"""
from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.typing import ConfigType

from .client import FoilsHidError, FreeboxPlayerHidClient, UnknownKey
from .const import ATTR_KEY, DOMAIN, FBX_REMOTE_KEYS, SERVICE_PRESS

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = []

ATTR_ENTRY_ID = "entry_id"

SERVICE_PRESS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_KEY): vol.In(sorted(FBX_REMOTE_KEYS)),
        vol.Optional(ATTR_ENTRY_ID): str,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration (register the local logo as a static asset)."""
    await _async_register_static_images(hass)
    return True


async def _async_register_static_images(hass: HomeAssistant) -> None:
    """Best-effort: serve logo.png so it can be shown in the config flow help text."""
    file_path = Path(__file__).parent / "logo.png"
    if not file_path.exists():
        return

    url_path = f"/{DOMAIN}/logo.png"
    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(url_path, str(file_path), True)]
        )
    except ImportError:
        try:
            hass.http.register_static_path(url_path, str(file_path), cache_headers=True)
        except Exception:  # pragma: no cover - purely cosmetic, never block setup
            _LOGGER.debug(
                "freebox_player_remote: could not register static path for logo.png",
                exc_info=True,
            )
    except Exception:  # pragma: no cover - purely cosmetic, never block setup
        _LOGGER.debug(
            "freebox_player_remote: could not register static path for logo.png",
            exc_info=True,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Freebox Player HID from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]

    client = FreeboxPlayerHidClient(host, port)
    try:
        await hass.async_add_executor_job(client.connect)
    except FoilsHidError as err:
        # Tear down whatever connect() may have partially set up (socket,
        # background threads) before discarding this client -- otherwise a
        # failed attempt leaks them, and HA retries this on every
        # ConfigEntryNotReady backoff cycle.
        await hass.async_add_executor_job(client.disconnect)
        # ConfigEntryNotReady tells HA to retry setup with backoff instead of
        # failing permanently -- the Player is often just off/rebooting.
        raise ConfigEntryNotReady(
            f"Cannot connect to Freebox Player at {host}:{port}: {err}"
        ) from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client

    _async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options/data change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the `press` service once, regardless of how many entries exist."""
    if hass.services.has_service(DOMAIN, SERVICE_PRESS):
        return

    async def _async_handle_press(call: ServiceCall) -> None:
        key = call.data[ATTR_KEY]
        entry_id = call.data.get(ATTR_ENTRY_ID)
        clients: dict[str, FreeboxPlayerHidClient] = hass.data.get(DOMAIN, {})

        if entry_id is not None:
            client = clients.get(entry_id)
            if client is None:
                raise HomeAssistantError(
                    f"No Freebox Player HID config entry with id '{entry_id}'"
                )
        elif len(clients) == 1:
            client = next(iter(clients.values()))
        elif not clients:
            raise HomeAssistantError("No Freebox Player HID device is configured")
        else:
            raise HomeAssistantError(
                "Multiple Freebox Player HID devices are configured; "
                "specify 'entry_id' to pick one"
            )

        try:
            await hass.async_add_executor_job(client.press, key)
        except UnknownKey as err:
            raise HomeAssistantError(str(err)) from err
        except FoilsHidError as err:
            raise HomeAssistantError(f"Failed to send key '{key}': {err}") from err

    hass.services.async_register(
        DOMAIN, SERVICE_PRESS, _async_handle_press, schema=SERVICE_PRESS_SCHEMA
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    clients: dict[str, FreeboxPlayerHidClient] = hass.data.get(DOMAIN, {})
    client = clients.pop(entry.entry_id, None)
    if client is not None:
        await hass.async_add_executor_job(client.disconnect)

    if not clients and hass.services.has_service(DOMAIN, SERVICE_PRESS):
        hass.services.async_remove(DOMAIN, SERVICE_PRESS)

    return True
