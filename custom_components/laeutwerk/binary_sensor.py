"""Binary sensor: a reminder of the rule is open (reminding)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    """Set up the open sensors."""

    def factory(manager: LaeutwerkManager, rule_id: str) -> list[Entity]:
        return [OpenSensor(manager, rule_id)]

    async_setup_rule_entities(entry, entry.runtime_data, factory, async_add_entities)


class OpenSensor(LaeutwerkEntity, BinarySensorEntity):
    """On while a reminder waits to be acknowledged."""

    _attr_translation_key = "open"

    def __init__(self, manager: LaeutwerkManager, rule_id: str) -> None:
        """Initialise the sensor."""
        super().__init__(
            manager, rule_id, "open", f"binary_sensor.laeutwerk_{rule_id}_offen"
        )

    @property
    def is_on(self) -> bool:
        """Return True while a reminder is open."""
        return bool(self.runner and self.runner.open_reminders)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Since when the oldest open reminder is reminding."""
        if not self.runner or not (open_reminders := self.runner.open_reminders):
            return None
        since = min(r.reminded_at for r in open_reminders if r.reminded_at)
        return {"since": since.isoformat(), "count": len(open_reminders)}
