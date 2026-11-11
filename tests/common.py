"""Test helpers: fake calendars, reference rules (SPEC B8) and time travel."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from custom_components.laeutwerk.const import DOMAIN
from custom_components.laeutwerk.manager import LaeutwerkManager

from .ha_testing import MockConfigEntry, async_fire_time_changed

TZ = ZoneInfo("Europe/Berlin")
WASTE = "calendar.abfallkalender"
KULT = "calendar.kult61"
PHONE = "notify.mobile_app_steven"


def at(day: date, hh: int, mm: int = 0) -> datetime:
    """Local (Europe/Berlin) time on a day."""
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=TZ)


class FakeCalendars:
    """Calendar entities backed by a dict, served via ``calendar.get_events``."""

    def __init__(self, hass: HomeAssistant, *entity_ids: str) -> None:
        self.hass = hass
        self.events: dict[str, list[dict[str, Any]]] = {}
        self.failing: set[str] = set()
        self.calls = 0
        for entity_id in entity_ids:
            self.events[entity_id] = []
            name = entity_id.split(".")[1].capitalize()
            hass.states.async_set(entity_id, "off", {"friendly_name": name})
        hass.services.async_register(
            "calendar",
            "get_events",
            self._get_events,
            supports_response=SupportsResponse.ONLY,
        )

    def add_all_day(
        self, entity_id: str, summary: str, day: date, **extra: Any
    ) -> None:
        self.events[entity_id].append(
            {
                "start": day.isoformat(),
                "end": (day + timedelta(days=1)).isoformat(),
                "summary": summary,
                **extra,
            }
        )

    def add_timed(
        self, entity_id: str, summary: str, start: datetime, hours: float = 4, **extra
    ) -> None:
        self.events[entity_id].append(
            {
                "start": start.isoformat(),
                "end": (start + timedelta(hours=hours)).isoformat(),
                "summary": summary,
                **extra,
            }
        )

    def remove(self, entity_id: str, summary: str) -> None:
        self.events[entity_id] = [
            e for e in self.events[entity_id] if e["summary"] != summary
        ]

    def touch(self, entity_id: str) -> None:
        """Change the entity state like a calendar does after an edit."""
        state = self.hass.states.get(entity_id)
        assert state is not None
        self.hass.states.async_set(
            entity_id, "off", {**state.attributes, "rev": self.calls}, force_update=True
        )

    @staticmethod
    def _bounds(event: dict[str, Any]) -> tuple[datetime, datetime]:
        def parse(value: str) -> datetime:
            if "T" in value:
                return datetime.fromisoformat(value)
            return datetime.fromisoformat(value).replace(tzinfo=TZ)

        return parse(event["start"]), parse(event["end"])

    async def _get_events(self, call: ServiceCall) -> dict[str, Any]:
        self.calls += 1
        start = dt_util.parse_datetime(call.data["start_date_time"])
        end = dt_util.parse_datetime(call.data["end_date_time"])
        assert start and end
        result: dict[str, Any] = {}
        entity_ids = call.data["entity_id"]
        for entity_id in [entity_ids] if isinstance(entity_ids, str) else entity_ids:
            if entity_id in self.failing:
                raise HomeAssistantError(f"{entity_id} is broken")
            result[entity_id] = {
                "events": [
                    dict(event)
                    for event in self.events[entity_id]
                    if self._bounds(event)[0] < end and self._bounds(event)[1] > start
                ]
            }
        return result


def muell_rule(**changes: Any) -> dict[str, Any]:
    """Reference rule "Müll rausstellen" (SPEC B8)."""
    rule: dict[str, Any] = {
        "id": "muell",
        "name": "Müll rausstellen",
        "sources": [WASTE],
        "filter": {
            "all_day": True,
            "keywords": {
                "columns": ["tonne", "farbe", "artikel"],
                "rows": [
                    {
                        "match": "Papier",
                        "tonne": "Papiertonne",
                        "farbe": "blau",
                        "artikel": "die",
                    },
                    {
                        "match": "Bio",
                        "tonne": "Biotonne",
                        "farbe": "grün",
                        "artikel": "die",
                    },
                    {
                        "match": "Rest",
                        "tonne": "Restmülltonne",
                        "farbe": "grau",
                        "artikel": "die",
                    },
                    {
                        "match": "Gelb",
                        "tonne": "gelben Sack",
                        "farbe": "gelb",
                        "artikel": "den",
                    },
                ],
            },
        },
        "reminders": [{"at": "-1d 17:00"}],
        "signals": [
            {
                "id": "push",
                "type": "notify",
                "targets": [PHONE],
                "title": "{wann}: {tonnen}",
                "message": "Bitte heute Abend {artikel} {tonne} rausstellen.",
                "message_plural": "Bitte heute Abend rausstellen: {tonnen}.",
                "actions": [{"ack": True, "label": "Steht draußen"}],
            }
        ],
        "acknowledge": [{"type": "notify_action"}],
        "ack_label": "Steht draußen",
        "bundle": True,
        "expire": "event_day 12:00",
    }
    rule.update(changes)
    return rule


def kult61_rule(**changes: Any) -> dict[str, Any]:
    """Reference rule "Kult61-Dienst" (SPEC B8)."""
    rule: dict[str, Any] = {
        "id": "kult61",
        "name": "Kult61-Dienst",
        "sources": [KULT],
        "filter": {"keywords": {"rows": [{"match": "Dienst:", "mode": "startswith"}]}},
        "reminders": [{"at": "-1d 20:00"}, {"at": "-2h"}],
        "signals": [
            {
                "id": "push",
                "type": "notify",
                "targets": [PHONE],
                "message": "Denk an deinen Dienst {wann}: {rest}, ab {uhrzeit}.",
                "actions": [{"ack": True, "label": "Bin dran"}],
            }
        ],
        "expire": "event_end",
    }
    rule.update(changes)
    return rule


async def setup_integration(
    hass: HomeAssistant,
) -> tuple[MockConfigEntry, LaeutwerkManager]:
    """Set up Läutwerk (Europe/Berlin, German)."""
    await hass.config.async_set_time_zone("Europe/Berlin")
    hass.config.language = "de"
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, entry.runtime_data


async def tick(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, when: datetime
) -> None:
    """Move the clock and let timers and tasks run."""
    freezer.move_to(when)
    async_fire_time_changed(hass, when)
    await hass.async_block_till_done()
    await hass.async_block_till_done()
