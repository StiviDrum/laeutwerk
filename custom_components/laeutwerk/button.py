"""Button: acknowledge the open reminder of a rule."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LaeutwerkConfigEntry
from .const import ACK_VIA_BUTTON
from .entity import LaeutwerkEntity, async_setup_rule_entities
from .manager import LaeutwerkManager, person_name

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LaeutwerkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the done buttons."""

    def factory(manager: LaeutwerkManager, rule_id: str) -> list[Entity]:
        return [DoneButton(manager, rule_id)]

    async_setup_rule_entities(entry, entry.runtime_data, factory, async_add_entities)


class DoneButton(LaeutwerkEntity, ButtonEntity):
    """Marks the open (or the upcoming) reminder as done."""

    _attr_translation_key = "done"

    def __init__(self, manager: LaeutwerkManager, rule_id: str) -> None:
        """Initialise the button."""
        super().__init__(
            manager, rule_id, "done", f"button.laeutwerk_{rule_id}_erledigt"
        )

    async def async_press(self) -> None:
        """Acknowledge."""
        await self._manager.async_acknowledge(
            self._rule_id,
            by=person_name(self.hass, self._context.user_id if self._context else None),
            via=ACK_VIA_BUTTON,
        )
