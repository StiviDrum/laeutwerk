"""Rule state and next-event sensors."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LaeutwerkConfigEntry
from .entity import LaeutwerkEntity, async_setup_rule_entities
from .manager import LaeutwerkManager, occurrence_payload
from .matching import render_headline
from .model import (
    STATE_DONE,
    STATE_INACTIVE,
    STATE_MISSED,
    STATE_PLANNED,
    STATE_REMINDED,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LaeutwerkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up rule sensors."""

    def factory(manager: LaeutwerkManager, rule_id: str) -> list[Entity]:
        return [StateSensor(manager, rule_id), NextEventSensor(manager, rule_id)]

    async_setup_rule_entities(entry, entry.runtime_data, factory, async_add_entities)


class StateSensor(LaeutwerkEntity, SensorEntity):
    """State of a rule: planned / reminded / done / missed / inactive."""

    _attr_name = None  # use the device (rule) name
    _attr_translation_key = "state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [  # noqa: RUF012
        STATE_PLANNED,
        STATE_REMINDED,
        STATE_DONE,
        STATE_MISSED,
        STATE_INACTIVE,
    ]
    _unrecorded_attributes = frozenset({"variables"})

    def __init__(self, manager: LaeutwerkManager, rule_id: str) -> None:
        """Initialise the sensor."""
        super().__init__(manager, rule_id, "state", f"sensor.laeutwerk_{rule_id}")

    @property
    def icon(self) -> str | None:
        """Icon of the rule."""
        return (self.rule.icon if self.rule else None) or "mdi:bell-ring-outline"

    @property
    def native_value(self) -> str:
        """State of the current reminder."""
        return self.runner.state if self.runner else STATE_INACTIVE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Attributes per SPEC B6."""
        attributes: dict[str, Any] = {"rule_id": self._rule_id, "headline": None}
        if (runner := self.runner) is None:
            return attributes
        upcoming = runner.next_occurrence()
        attributes["next_event"] = upcoming.start.isoformat() if upcoming else None
        current = runner.current()
        if current is not None:
            attributes |= {
                "reminder_id": current.id,
                "event_title": current.events[0].summary if current.events else None,
                "event_start": current.start.isoformat(),
                "bundled_titles": [event.summary for event in current.events],
                "variables": runner.variables(current),
                "headline": render_headline(
                    runner.rule, current.events, runner.variables(current)
                ),
                "acknowledged_by": current.acknowledged_by,
                "acknowledged_at": (
                    current.finished_at.isoformat()
                    if current.state == STATE_DONE and current.finished_at
                    else None
                ),
            }
            if current.snoozed_until:
                attributes["snoozed_until"] = current.snoozed_until.isoformat()
        if runner.errors:
            attributes["errors"] = dict(runner.errors)
        return attributes


class NextEventSensor(LaeutwerkEntity, SensorEntity):
    """Start of the next matching event."""

    _attr_translation_key = "next_event"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, manager: LaeutwerkManager, rule_id: str) -> None:
        """Initialise the sensor."""
        super().__init__(
            manager,
            rule_id,
            "next_event",
            f"sensor.laeutwerk_{rule_id}_naechster_termin",
        )

    @property
    def native_value(self) -> datetime | None:
        """Start of the next match."""
        if (runner := self.runner) is None:
            return None
        upcoming = runner.next_occurrence()
        return upcoming.start if upcoming else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Title and days until the next match."""
        if (runner := self.runner) is None:
            return None
        payload = occurrence_payload(runner, runner.next_occurrence())
        if payload is None:
            return None
        return {
            "title": payload["variables"].get("titel"),
            "titles": payload["titles"],
            "days_until": payload["days_until"],
        }
