"""Diagnostics download (Settings → Devices & services → Läutwerk / a rule device).

Contains the rules as stored, their runtime status (reminders with
variables) and the history – what is needed to reproduce a problem. There are
no credentials in Läutwerk data; event titles stay readable.
"""

from __future__ import annotations

from typing import Any

from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.loader import async_get_integration

from . import LaeutwerkConfigEntry
from .const import DOMAIN
from .issues import rule_action_refs, rule_entity_refs
from .manager import LaeutwerkManager


def _rule_diagnostics(manager: LaeutwerkManager, rule_id: str) -> dict[str, Any]:
    rule = manager.rules[rule_id]
    return {
        "rule": rule.to_dict(),
        "status": manager.status(rule_id),
        "history": manager.history.get(rule_id, []),
        "references": {
            "entities": sorted(rule_entity_refs(rule)),
            "actions": sorted(rule_action_refs(rule)),
        },
    }


async def _header(hass: HomeAssistant) -> dict[str, Any]:
    integration = await async_get_integration(hass, DOMAIN)
    return {
        "laeutwerk_version": str(integration.version),
        "home_assistant_version": HA_VERSION,
        "time_zone": hass.config.time_zone,
        "language": hass.config.language,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LaeutwerkConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for all rules."""
    manager = entry.runtime_data
    return {
        **await _header(hass),
        "rules": [_rule_diagnostics(manager, rule_id) for rule_id in manager.rules],
        "invalid_rules": manager.invalid_rules,
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: LaeutwerkConfigEntry, device: dr.DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for the rule of one device."""
    manager = entry.runtime_data
    rule_id = next(
        (ident for domain, ident in device.identifiers if domain == DOMAIN), None
    )
    if rule_id is None or rule_id not in manager.rules:
        return {**await _header(hass), "rule": None}
    return {**await _header(hass), **_rule_diagnostics(manager, rule_id)}
