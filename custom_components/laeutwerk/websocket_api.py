"""Websocket API used by the card."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import timedelta
import functools
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .compat import vol
from .const import DOMAIN, HISTORY_MAX, LOOKAHEAD_DAYS
from .engine import RuleRunner
from .manager import (
    EVENT_REMOVED,
    LaeutwerkManager,
    RuleNotFoundError,
    occurrence_payload,
)
from .matching import build_occurrences
from .model import Rule
from .schema import validate_rule
from .sources import async_fetch_events
from .timespec import local_instant

MAX_PREVIEW = 10

type _Handler = Callable[
    [HomeAssistant, websocket_api.ActiveConnection, dict[str, Any], LaeutwerkManager],
    Coroutine[Any, Any, None],
]


def rule_payload(manager: LaeutwerkManager, rule: Rule) -> dict[str, Any]:
    """Rule configuration plus runtime status."""
    return {**rule.to_dict(), "status": manager.status(rule.id)}


def _with_manager(func: _Handler) -> Callable[..., Coroutine[Any, Any, None]]:
    """Resolve the manager and turn errors into websocket errors."""

    @functools.wraps(func)
    async def wrapper(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
    ) -> None:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            connection.send_error(msg["id"], "not_loaded", "Läutwerk is not set up")
            return
        try:
            await func(hass, connection, msg, entries[0].runtime_data)
        except RuleNotFoundError as err:
            connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, str(err))
        except (vol.Invalid, ValueError) as err:
            connection.send_error(msg["id"], websocket_api.ERR_INVALID_FORMAT, str(err))
        except HomeAssistantError as err:
            connection.send_error(
                msg["id"], websocket_api.ERR_HOME_ASSISTANT_ERROR, str(err)
            )

    return wrapper


@websocket_api.websocket_command({vol.Required("type"): "laeutwerk/rules/list"})
@websocket_api.async_response
@_with_manager
async def ws_list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    manager: LaeutwerkManager,
) -> None:
    """List all rules."""
    rules = [rule_payload(manager, rule) for rule in manager.rules.values()]
    connection.send_result(msg["id"], {"rules": rules})


@websocket_api.websocket_command(
    {vol.Required("type"): "laeutwerk/rules/get", vol.Required("rule_id"): cv.string}
)
@websocket_api.async_response
@_with_manager
async def ws_get(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    manager: LaeutwerkManager,
) -> None:
    """Return one rule."""
    rule = manager.get_rule(msg["rule_id"])
    connection.send_result(msg["id"], rule_payload(manager, rule))


@websocket_api.websocket_command(
    {vol.Required("type"): "laeutwerk/rules/create", vol.Required("rule"): dict}
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_manager
async def ws_create(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    manager: LaeutwerkManager,
) -> None:
    """Create a rule (admin)."""
    rule = await manager.async_create_rule(msg["rule"])
    connection.send_result(msg["id"], rule_payload(manager, rule))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "laeutwerk/rules/update",
        vol.Required("rule_id"): cv.string,
        vol.Required("rule"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_manager
async def ws_update(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    manager: LaeutwerkManager,
) -> None:
    """Replace a rule (admin)."""
    data = {key: value for key, value in msg["rule"].items() if key != "status"}
    rule = await manager.async_update_rule(msg["rule_id"], data)
    connection.send_result(msg["id"], rule_payload(manager, rule))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "laeutwerk/rules/duplicate",
        vol.Required("rule_id"): cv.string,
        vol.Optional("name"): cv.string,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_manager
async def ws_duplicate(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    manager: LaeutwerkManager,
) -> None:
    """Copy a rule; the copy starts switched off (admin)."""
    rule = await manager.async_duplicate_rule(msg["rule_id"], msg.get("name"))
    connection.send_result(msg["id"], rule_payload(manager, rule))


@websocket_api.websocket_command(
    {vol.Required("type"): "laeutwerk/rules/delete", vol.Required("rule_id"): cv.string}
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_manager
async def ws_delete(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    manager: LaeutwerkManager,
) -> None:
    """Delete a rule (admin)."""
    await manager.async_delete_rule(msg["rule_id"])
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "laeutwerk/rules/subscribe",
        vol.Optional("rule_id"): cv.string,
    }
)
@websocket_api.async_response
@_with_manager
async def ws_subscribe(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    manager: LaeutwerkManager,
) -> None:
    """Send all (or one) rules now and on every change."""
    only = msg.get("rule_id")
    if only is not None:
        manager.get_rule(only)

    @callback
    def forward(event: str, rule_id: str) -> None:
        if only is not None and rule_id != only:
            return
        rule = manager.rules.get(rule_id)
        connection.send_message(
            websocket_api.event_message(
                msg["id"],
                {
                    "event": event,
                    "rule_id": rule_id,
                    "rule": None
                    if event == EVENT_REMOVED or rule is None
                    else rule_payload(manager, rule),
                },
            )
        )

    connection.subscriptions[msg["id"]] = manager.async_add_listener(forward)
    connection.send_result(msg["id"])
    rules = [
        rule_payload(manager, rule)
        for rule in manager.rules.values()
        if only is None or rule.id == only
    ]
    connection.send_message(
        websocket_api.event_message(msg["id"], {"event": "init", "rules": rules})
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "laeutwerk/preview",
        vol.Exclusive("rule_id", "rule"): cv.string,
        vol.Exclusive("rule", "rule"): dict,
        vol.Optional("limit", default=5): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_PREVIEW)
        ),
    }
)
@websocket_api.async_response
@_with_manager
async def ws_preview(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    manager: LaeutwerkManager,
) -> None:
    """Next matching events of a saved or an unsaved rule, with variables."""
    if "rule" in msg:
        data = {key: value for key, value in msg["rule"].items() if key != "status"}
        data.setdefault("id", "preview")
        data.setdefault("name", "Preview")
        data.setdefault("reminders", [{"at": "event_day 00:00"}])
        rule = Rule.from_dict(validate_rule(data))
    elif "rule_id" in msg:
        rule = manager.get_rule(msg["rule_id"])
    else:
        raise vol.Invalid("rule_id or rule is required")

    now = dt_util.utcnow()
    tz = dt_util.get_default_time_zone()
    events, errors = await async_fetch_events(
        hass,
        rule.sources,
        local_instant(now.astimezone(tz).date(), 0, tz),
        now + timedelta(days=LOOKAHEAD_DAYS),
    )
    runner = RuleRunner(
        hass, rule, {}, on_update=lambda _runner: None, on_changed=lambda: None
    )
    occurrences = sorted(build_occurrences(rule, events), key=lambda o: o.start)
    items = []
    for occurrence in [o for o in occurrences if o.end > now][: msg["limit"]]:
        payload = occurrence_payload(runner, occurrence) or {}
        payload["reminder_times"] = [
            when.isoformat() for _at, when in runner.reminder_times(occurrence)
        ]
        payload["expires_at"] = runner.expire_at(occurrence).isoformat()
        items.append(payload)
    connection.send_result(
        msg["id"],
        {
            "events": items,
            "total_events": len(events),
            "errors": errors,
            "variables": sorted(runner.variables(occurrences[0]))
            if occurrences
            else [],
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "laeutwerk/history",
        vol.Required("rule_id"): cv.string,
        vol.Optional("limit", default=20): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=HISTORY_MAX)
        ),
    }
)
@websocket_api.async_response
@_with_manager
async def ws_history(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    manager: LaeutwerkManager,
) -> None:
    """Finished reminders of a rule, newest first."""
    manager.get_rule(msg["rule_id"])
    entries = manager.history.get(msg["rule_id"], [])[: msg["limit"]]
    connection.send_result(msg["id"], {"history": entries})


@websocket_api.websocket_command({vol.Required("type"): "laeutwerk/templates/list"})
@websocket_api.async_response
@_with_manager
async def ws_templates_list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    manager: LaeutwerkManager,
) -> None:
    """Built-in and own templates."""
    connection.send_result(msg["id"], {"templates": manager.list_templates()})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "laeutwerk/templates/save",
        vol.Required("name"): cv.string,
        vol.Optional("description", default=""): cv.string,
        vol.Exclusive("rule_id", "rule"): cv.string,
        vol.Exclusive("rule", "rule"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_manager
async def ws_templates_save(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    manager: LaeutwerkManager,
) -> None:
    """Save a rule (saved or unsaved) as own template (admin)."""
    if "rule_id" in msg:
        rule = manager.get_rule(msg["rule_id"]).to_dict()
    elif "rule" in msg:
        rule = msg["rule"]
    else:
        raise vol.Invalid("rule_id or rule is required")
    template = manager.save_template(msg["name"], rule, msg["description"])
    connection.send_result(msg["id"], template)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "laeutwerk/templates/delete",
        vol.Required("template_id"): cv.string,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_manager
async def ws_templates_delete(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    manager: LaeutwerkManager,
) -> None:
    """Delete an own template (admin)."""
    manager.delete_template(msg["template_id"])
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "laeutwerk/rules/export",
        vol.Optional("rule_ids"): [cv.string],
    }
)
@websocket_api.async_response
@_with_manager
async def ws_export(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    manager: LaeutwerkManager,
) -> None:
    """YAML of some or all rules."""
    rule_ids = msg.get("rule_ids") or list(manager.rules)
    connection.send_result(msg["id"], {"yaml": manager.export_rules(rule_ids)})


@websocket_api.websocket_command(
    {vol.Required("type"): "laeutwerk/rules/import", vol.Required("yaml"): cv.string}
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_manager
async def ws_import(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    manager: LaeutwerkManager,
) -> None:
    """Create rules from YAML (admin)."""
    rules = await manager.async_import_rules(msg["yaml"])
    connection.send_result(
        msg["id"], {"rules": [rule_payload(manager, rule) for rule in rules]}
    )


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    """Register all websocket commands."""
    for command in (
        ws_list,
        ws_get,
        ws_create,
        ws_update,
        ws_duplicate,
        ws_delete,
        ws_subscribe,
        ws_preview,
        ws_history,
        ws_templates_list,
        ws_templates_save,
        ws_templates_delete,
        ws_export,
        ws_import,
    ):
        websocket_api.async_register_command(hass, command)
