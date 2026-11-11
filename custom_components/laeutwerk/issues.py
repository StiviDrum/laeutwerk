"""Repair issues for rules that refer to entities or actions which do not exist."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er, issue_registry as ir

from .const import DOMAIN
from .model import Rule

ISSUE_MISSING = "missing_entities"


def _entity_ids(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, str) and "." in v and "{" not in v]


def _walk(node: Any, found: set[str]) -> None:
    """Collect ``entity_id`` values (incl. ``target.entity_id``) recursively."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "entity_id":
                found.update(_entity_ids(value))
            else:
                _walk(value, found)
    elif isinstance(node, list):
        for item in node:
            _walk(item, found)


def rule_entity_refs(rule: Rule) -> set[str]:
    """All entity ids a rule refers to (sources, signals, triggers, conditions)."""
    found: set[str] = set(rule.sources)
    for signal in rule.signals:
        config = signal.config
        for key in ("entities", "players", "persons"):
            found.update(_entity_ids(config.get(key)))
        found.update(_entity_ids(config.get("tts")))
        _walk(config.get("conditions"), found)
        _walk(config.get("actions") if signal.type == "action" else None, found)
        _walk(signal.opportunity, found)
    for ack in rule.acknowledge:
        _walk(ack.get("trigger"), found)
    _walk((rule.activation or {}).get("conditions"), found)
    _walk(rule.on_done, found)
    found.update((rule.assignee or {}).get("persons", []))
    return found


def rule_action_refs(rule: Rule) -> set[str]:
    """Notify actions a rule calls directly (``targets`` of push signals)."""
    return {
        target
        for signal in rule.signals
        for target in signal.config.get("targets", [])
        if isinstance(target, str)
    }


def issue_id(rule_id: str) -> str:
    """Repair issue id of a rule."""
    return f"{ISSUE_MISSING}_{rule_id}"


@callback
def async_check_rule(hass: HomeAssistant, rule: Rule) -> list[str]:
    """Create or remove the repair issue of a rule; return what is missing."""
    if not rule.enabled:
        async_clear_rule(hass, rule.id)
        return []
    registry = er.async_get(hass)
    missing = sorted(
        entity_id
        for entity_id in rule_entity_refs(rule)
        if hass.states.get(entity_id) is None and registry.async_get(entity_id) is None
    )
    missing += sorted(
        action
        for action in rule_action_refs(rule)
        if not hass.services.has_service(*action.split(".", 1))
    )
    if missing:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id(rule.id),
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_MISSING,
            translation_placeholders={
                "rule": rule.name,
                "entities": ", ".join(missing),
            },
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id(rule.id))
    return missing


@callback
def async_clear_rule(hass: HomeAssistant, rule_id: str) -> None:
    """Remove the repair issue of a deleted or disabled rule."""
    ir.async_delete_issue(hass, DOMAIN, issue_id(rule_id))
