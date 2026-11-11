"""Services: acknowledge and trigger reminders, read and edit rules.

Everything the card can do is also available as a service, so automations
and assistants (e.g. via an MCP connection) can operate Läutwerk. Editing
services require an admin user (calls without a user, e.g. from automations,
are allowed).
"""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
    Unauthorized,
)
from homeassistant.helpers import config_validation as cv

from .compat import vol
from .const import ACK_VIA_SERVICE, DOMAIN
from .durations import duration_minutes
from .manager import LaeutwerkManager, RuleNotFoundError, person_name

SERVICE_ACKNOWLEDGE = "acknowledge"
SERVICE_SNOOZE = "snooze"
SERVICE_TRIGGER = "trigger"
SERVICE_TEST_SIGNAL = "test_signal"
SERVICE_GET_RULES = "get_rules"
SERVICE_CREATE_RULE = "create_rule"
SERVICE_UPDATE_RULE = "update_rule"
SERVICE_DELETE_RULE = "delete_rule"
SERVICE_DUPLICATE_RULE = "duplicate_rule"
SERVICE_EXPORT_RULES = "export_rules"
SERVICE_IMPORT_RULES = "import_rules"
SERVICE_ENABLE = "enable"
SERVICE_DISABLE = "disable"

ATTR_RULE = "rule"

_RULE_SCHEMA = vol.Schema({vol.Required(ATTR_RULE): cv.string})
# One rule id, a list of ids, or nothing (= all rules).
_RULES_SCHEMA = vol.Schema(
    {vol.Optional(ATTR_RULE): vol.All(cv.ensure_list, [cv.string])}
)


def get_manager(hass: HomeAssistant) -> LaeutwerkManager:
    """Return the manager of the loaded config entry."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_loaded"
        )
    return entries[0].runtime_data


def _unknown_rule(rule_id: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="unknown_rule",
        translation_placeholders={"rule": rule_id},
    )


def _check_rule(manager: LaeutwerkManager, rule_id: str) -> None:
    if rule_id not in manager.rules:
        raise _unknown_rule(rule_id)


def _rule_ids(hass: HomeAssistant, call: ServiceCall) -> list[str]:
    """Rule ids of a call with an optional rule / rule list (default: all)."""
    manager = get_manager(hass)
    ids: list[str] = call.data.get(ATTR_RULE) or list(manager.rules)
    for rule_id in ids:
        _check_rule(manager, rule_id)
    return ids


async def _require_admin(hass: HomeAssistant, call: ServiceCall) -> None:
    """Editing needs an admin; calls without a user (automations) are allowed."""
    if call.context.user_id is None:
        return
    user = await hass.auth.async_get_user(call.context.user_id)
    if user is None or not user.is_admin:
        raise Unauthorized(context=call.context)


def rule_overview(manager: LaeutwerkManager, rule_id: str) -> dict[str, Any]:
    """Rule dict plus runtime status (get_rules, websocket)."""
    return {
        **copy.deepcopy(manager.get_rule(rule_id).to_dict()),
        "status": manager.status(rule_id),
    }


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register Läutwerk services."""

    async def acknowledge(call: ServiceCall) -> ServiceResponse:
        manager = get_manager(hass)
        rule_id: str | None = call.data.get(ATTR_RULE)
        if rule_id is not None:
            _check_rule(manager, rule_id)
        done = await manager.async_acknowledge(
            rule_id,
            reminder_id=call.data.get("reminder_id"),
            by=call.data.get("person") or person_name(hass, call.context.user_id),
            via=ACK_VIA_SERVICE,
        )
        if not call.return_response:
            return None
        return {"acknowledged": [reminder.id for reminder in done]}

    async def snooze(call: ServiceCall) -> ServiceResponse:
        manager = get_manager(hass)
        rule_id: str | None = call.data.get(ATTR_RULE)
        if rule_id is not None:
            _check_rule(manager, rule_id)
        snoozed = await manager.async_snooze(
            call.data["duration"], rule_id, reminder_id=call.data.get("reminder_id")
        )
        if not call.return_response:
            return None
        return {"snoozed": [reminder.id for reminder in snoozed]}

    async def trigger(call: ServiceCall) -> None:
        manager = get_manager(hass)
        rule_id = call.data[ATTR_RULE]
        _check_rule(manager, rule_id)
        runner = manager.runners.get(rule_id)
        if runner is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="rule_disabled",
                translation_placeholders={"rule": rule_id},
            )
        await runner.async_refresh()
        if await runner.async_trigger() is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_upcoming_event",
                translation_placeholders={"rule": rule_id},
            )

    async def test_signal(call: ServiceCall) -> None:
        manager = get_manager(hass)
        rule_id = call.data[ATTR_RULE]
        _check_rule(manager, rule_id)
        if ("signal" in call.data) == ("config" in call.data):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="signal_or_config"
            )
        if "config" in call.data:
            await _require_admin(hass, call)
        try:
            sent = await manager.async_test_signal(
                rule_id, call.data.get("signal"), call.data.get("config")
            )
        except (vol.Invalid, ValueError, HomeAssistantError) as err:
            raise ServiceValidationError(str(err)) from err
        if not sent:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="signal_failed"
            )

    async def get_rules(call: ServiceCall) -> ServiceResponse:
        manager = get_manager(hass)
        return {
            "rules": [
                rule_overview(manager, rule_id) for rule_id in _rule_ids(hass, call)
            ]
        }

    async def create_rule(call: ServiceCall) -> ServiceResponse:
        await _require_admin(hass, call)
        try:
            rule = await get_manager(hass).async_create_rule(call.data["config"])
        except (vol.Invalid, ValueError, HomeAssistantError) as err:
            raise ServiceValidationError(str(err)) from err
        return {"rule": rule.id} if call.return_response else None

    async def update_rule(call: ServiceCall) -> None:
        await _require_admin(hass, call)
        manager = get_manager(hass)
        rule_id = call.data[ATTR_RULE]
        _check_rule(manager, rule_id)
        data = copy.deepcopy(manager.get_rule(rule_id).to_dict())
        data.update(call.data["config"])
        try:
            await manager.async_update_rule(rule_id, data)
        except (vol.Invalid, ValueError, HomeAssistantError) as err:
            raise ServiceValidationError(str(err)) from err

    async def delete_rule(call: ServiceCall) -> None:
        await _require_admin(hass, call)
        try:
            await get_manager(hass).async_delete_rule(call.data[ATTR_RULE])
        except RuleNotFoundError as err:
            raise _unknown_rule(call.data[ATTR_RULE]) from err

    async def duplicate_rule(call: ServiceCall) -> ServiceResponse:
        await _require_admin(hass, call)
        manager = get_manager(hass)
        _check_rule(manager, call.data[ATTR_RULE])
        try:
            rule = await manager.async_duplicate_rule(
                call.data[ATTR_RULE], call.data.get("name"), call.data.get("new_rule")
            )
        except (vol.Invalid, ValueError, HomeAssistantError) as err:
            raise ServiceValidationError(str(err)) from err
        return {"rule": rule.id} if call.return_response else None

    async def export_rules(call: ServiceCall) -> ServiceResponse:
        manager = get_manager(hass)
        return {"yaml": manager.export_rules(_rule_ids(hass, call))}

    async def import_rules(call: ServiceCall) -> ServiceResponse:
        await _require_admin(hass, call)
        try:
            rules = await get_manager(hass).async_import_rules(call.data["yaml"])
        except (vol.Invalid, ValueError, HomeAssistantError) as err:
            raise ServiceValidationError(str(err)) from err
        return {"rules": [rule.id for rule in rules]} if call.return_response else None

    async def enable(call: ServiceCall) -> None:
        manager = get_manager(hass)
        for rule_id in _rule_ids(hass, call):
            await manager.async_set_enabled(rule_id, True)

    async def disable(call: ServiceCall) -> None:
        manager = get_manager(hass)
        for rule_id in _rule_ids(hass, call):
            await manager.async_set_enabled(rule_id, False)

    register = hass.services.async_register
    register(
        DOMAIN,
        SERVICE_ACKNOWLEDGE,
        acknowledge,
        vol.Schema(
            {
                vol.Optional(ATTR_RULE): cv.string,
                vol.Optional("reminder_id"): cv.string,
                vol.Optional("person"): cv.string,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    register(
        DOMAIN,
        SERVICE_SNOOZE,
        snooze,
        vol.Schema(
            {
                vol.Optional(ATTR_RULE): cv.string,
                vol.Optional("reminder_id"): cv.string,
                vol.Required("duration"): duration_minutes,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    register(DOMAIN, SERVICE_TRIGGER, trigger, _RULE_SCHEMA)
    register(
        DOMAIN,
        SERVICE_TEST_SIGNAL,
        test_signal,
        _RULE_SCHEMA.extend(
            {vol.Optional("signal"): cv.string, vol.Optional("config"): dict}
        ),
    )
    register(
        DOMAIN,
        SERVICE_GET_RULES,
        get_rules,
        _RULES_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    register(
        DOMAIN,
        SERVICE_CREATE_RULE,
        create_rule,
        vol.Schema({vol.Required("config"): dict}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    register(
        DOMAIN,
        SERVICE_UPDATE_RULE,
        update_rule,
        _RULE_SCHEMA.extend({vol.Required("config"): dict}),
    )
    register(DOMAIN, SERVICE_DELETE_RULE, delete_rule, _RULE_SCHEMA)
    register(
        DOMAIN,
        SERVICE_DUPLICATE_RULE,
        duplicate_rule,
        _RULE_SCHEMA.extend(
            {vol.Optional("name"): cv.string, vol.Optional("new_rule"): cv.slug}
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    register(
        DOMAIN,
        SERVICE_EXPORT_RULES,
        export_rules,
        _RULES_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    register(
        DOMAIN,
        SERVICE_IMPORT_RULES,
        import_rules,
        vol.Schema({vol.Required("yaml"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    register(DOMAIN, SERVICE_ENABLE, enable, _RULES_SCHEMA)
    register(DOMAIN, SERVICE_DISABLE, disable, _RULES_SCHEMA)
