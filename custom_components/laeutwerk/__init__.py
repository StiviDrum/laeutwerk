"""Läutwerk – reminders from calendar events that stay open until acknowledged."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from homeassistant.components.frontend import (
    add_extra_js_url,
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    CARD_FILENAME,
    CARD_URL_BASE,
    DOMAIN,
    PANEL_ELEMENT,
    PANEL_FILENAME,
    PANEL_URL_PATH,
)
from .manager import LaeutwerkManager
from .services import async_setup_services
from .websocket_api import async_register_websocket

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CARD_PATH = Path(__file__).parent / "frontend" / CARD_FILENAME

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]

type LaeutwerkConfigEntry = ConfigEntry[LaeutwerkManager]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register card, services and websocket API once per Home Assistant start."""
    async_setup_services(hass)
    async_register_websocket(hass)
    await _async_register_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LaeutwerkConfigEntry) -> bool:
    """Set up Läutwerk from a config entry."""
    manager = LaeutwerkManager(hass, entry.entry_id)
    await manager.async_setup()
    entry.runtime_data = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_register_panel(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LaeutwerkConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_unload()
        async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
    return unloaded


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the card JS and add it to the frontend (no manual resource needed)."""
    card_path = CARD_PATH

    def _bundle_hash() -> str | None:
        if not card_path.is_file():
            return None
        return hashlib.sha256(card_path.read_bytes()).hexdigest()[:12]

    digest = await hass.async_add_executor_job(_bundle_hash)
    if digest is None:
        _LOGGER.warning(
            "Card bundle %s not found – build the frontend (npm run build)", card_path
        )
        return

    # The whole directory: the card loads hashed chunks lazily.
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL_BASE, str(card_path.parent), cache_headers=True)]
    )
    url = f"{CARD_URL_BASE}/{CARD_FILENAME}"
    # Content hash busts the browser cache after updates and dev rebuilds.
    add_extra_js_url(hass, f"{url}?v={digest}")


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Add the admin sidebar panel (module served from the card's static dir)."""
    panel_path = CARD_PATH.parent / PANEL_FILENAME

    def _digest() -> str | None:
        if not panel_path.is_file():
            return None
        return hashlib.sha256(panel_path.read_bytes()).hexdigest()[:12]

    digest = await hass.async_add_executor_job(_digest)
    if digest is None:
        _LOGGER.debug("Panel bundle %s not found – panel not registered", panel_path)
        return
    # Same shape panel_custom registers; avoids an extra manifest dependency.
    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="Läutwerk",
        sidebar_icon="mdi:bell-ring-outline",
        frontend_url_path=PANEL_URL_PATH,
        config={
            "_panel_custom": {
                "name": PANEL_ELEMENT,
                "embed_iframe": False,
                "trust_external": False,
                "handle_safe_area": False,
                "module_url": f"{CARD_URL_BASE}/{PANEL_FILENAME}?v={digest}",
            }
        },
        require_admin=True,
        update=True,
    )
