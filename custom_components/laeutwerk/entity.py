"""Base entity: one device per rule, updated via dispatcher."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, NAME, SIGNAL_RULE_STATUS
from .engine import RuleRunner
from .manager import EVENT_ADDED, LaeutwerkManager
from .model import Rule


class LaeutwerkEntity(Entity):
    """Entity belonging to one rule."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self, manager: LaeutwerkManager, rule_id: str, key: str, entity_id: str
    ) -> None:
        """Initialise; entity ids follow SPEC B6 (<domain>.laeutwerk_<rule>...)."""
        self._manager = manager
        self._rule_id = rule_id
        self._attr_unique_id = f"{rule_id}_{key}"
        self.entity_id = entity_id
        rule = manager.rules[rule_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, rule_id)},
            name=rule.name,
            manufacturer=NAME,
            model="Rule",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def rule(self) -> Rule | None:
        """Current rule object (replaced on updates)."""
        return self._manager.rules.get(self._rule_id)

    @property
    def runner(self) -> RuleRunner | None:
        """Runner of the rule (None while the rule is off or HA is starting)."""
        return self._manager.runners.get(self._rule_id)

    @property
    def available(self) -> bool:
        """Available while the rule exists."""
        return self.rule is not None

    async def async_added_to_hass(self) -> None:
        """Subscribe to status updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_RULE_STATUS.format(self._rule_id),
                self.async_write_ha_state,
            )
        )


def async_setup_rule_entities(
    entry: ConfigEntry,
    manager: LaeutwerkManager,
    factory: Callable[[LaeutwerkManager, str], list[Entity]],
    add_entities: Callable[[list[Entity]], None],
) -> None:
    """Add entities for existing rules and for rules created later."""
    entities: list[Entity] = []
    for rule_id in manager.rules:
        entities += factory(manager, rule_id)
    add_entities(entities)

    @callback
    def _rule_event(event: str, rule_id: str) -> None:
        if event == EVENT_ADDED:
            add_entities(factory(manager, rule_id))

    entry.async_on_unload(manager.async_add_listener(_rule_event))
