"""Rule on/off switch (switch.laeutwerk_<rule>)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LaeutwerkConfigEntry
from .entity import LaeutwerkEntity, async_setup_rule_entities
from .manager import LaeutwerkManager

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LaeutwerkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up rule switches."""

    def factory(manager: LaeutwerkManager, rule_id: str) -> list[Entity]:
        return [RuleSwitch(manager, rule_id)]

    async_setup_rule_entities(entry, entry.runtime_data, factory, async_add_entities)


class RuleSwitch(LaeutwerkEntity, SwitchEntity):
    """Enables or disables a rule."""

    _attr_translation_key = "rule"

    def __init__(self, manager: LaeutwerkManager, rule_id: str) -> None:
        """Initialise the switch."""
        super().__init__(manager, rule_id, "enabled", f"switch.laeutwerk_{rule_id}")

    @property
    def is_on(self) -> bool | None:
        """Return True if the rule is enabled."""
        return self.rule.enabled if self.rule else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the rule."""
        await self._manager.async_set_enabled(self._rule_id, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the rule."""
        await self._manager.async_set_enabled(self._rule_id, False)
        self.async_write_ha_state()
