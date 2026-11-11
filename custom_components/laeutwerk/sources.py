"""Read events from the sources of a rule.

=====================  ======================================================
``calendar.*``         events via the ``calendar.get_events`` action
``todo.*``             open items with a due date via ``todo.get_items``
``date.*``             the date of the entity (all-day event)
``datetime.*``         the date and time of the entity
``input_datetime.*``   date (all-day) or date and time of the helper
``sensor.*``           a timestamp or date sensor (state is a date / time)
=====================  ======================================================

Single-date entities become one event titled with the entity name.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta, tzinfo
import logging
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .compat import vol
from .matching import parse_event
from .model import CalendarEvent
from .timespec import local_instant

_LOGGER = logging.getLogger(__name__)

CALENDAR_DOMAIN = "calendar"
TODO_DOMAIN = "todo"
DATE_DOMAINS = ("date", "datetime", "input_datetime", "sensor")
SOURCE_DOMAINS = (CALENDAR_DOMAIN, TODO_DOMAIN, *DATE_DOMAINS)


async def _async_call(
    hass: HomeAssistant, domain: str, service: str, data: dict[str, Any], entity_id: str
) -> list[dict[str, Any]]:
    response = await hass.services.async_call(
        domain, service, data, blocking=True, return_response=True
    )
    result = (response or {}).get(entity_id) or {}
    key = "events" if domain == CALENDAR_DOMAIN else "items"
    return list(result.get(key, []))  # type: ignore[union-attr]


def todo_item_event(
    entity_id: str, item: dict[str, Any], tz: tzinfo
) -> CalendarEvent | None:
    """Convert an open to-do item with a due date into an event."""
    due = item.get("due")
    if not due or item.get("status", "needs_action") != "needs_action":
        return None
    raw: dict[str, Any] = {
        "summary": item.get("summary", ""),
        "description": item.get("description") or "",
    }
    due = str(due)
    if "T" in due or " " in due:
        raw["start"] = raw["end"] = due.replace(" ", "T")
    else:
        raw["start"] = due
        raw["end"] = (date.fromisoformat(due) + timedelta(days=1)).isoformat()
    return parse_event(entity_id, raw, tz)


def state_event(state: State, tz: tzinfo) -> CalendarEvent | None:
    """Convert the state of a date / time entity into an event (None if unset)."""
    value = state.state
    if value in (STATE_UNKNOWN, STATE_UNAVAILABLE, ""):
        return None
    if state.domain == "input_datetime" and not state.attributes.get("has_date", True):
        return None  # time-only helper
    title = state.name
    if len(value) == 10 and (day := dt_util.parse_date(value)) is not None:
        start = local_instant(day, 0, tz)
        end = local_instant(day + timedelta(days=1), 0, tz)
        return CalendarEvent(
            calendar=state.entity_id,
            summary=title,
            start=start,
            end=end,
            all_day=True,
            day=day,
        )
    if (moment := dt_util.parse_datetime(value)) is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=tz)
    moment = moment.astimezone(UTC)
    return CalendarEvent(
        calendar=state.entity_id,
        summary=title,
        start=moment,
        end=moment,
        all_day=False,
        day=moment.astimezone(tz).date(),
    )


async def async_fetch_events(
    hass: HomeAssistant, entity_ids: Iterable[str], start: datetime, end: datetime
) -> tuple[list[CalendarEvent], dict[str, str]]:
    """Return the events of some sources and an error text per failed one."""
    tz = dt_util.get_default_time_zone()
    events: list[CalendarEvent] = []
    errors: dict[str, str] = {}
    for entity_id in entity_ids:
        domain = entity_id.split(".", 1)[0]
        state = hass.states.get(entity_id)
        if state is None:
            errors[entity_id] = "entity not found"
            continue
        if domain in DATE_DOMAINS:
            event = state_event(state, tz)
            if event is not None and event.end >= start and event.start < end:
                events.append(event)
            continue
        try:
            if domain == CALENDAR_DOMAIN:
                raw_events = await _async_call(
                    hass,
                    CALENDAR_DOMAIN,
                    "get_events",
                    {
                        "entity_id": entity_id,
                        "start_date_time": start.isoformat(),
                        "end_date_time": end.isoformat(),
                    },
                    entity_id,
                )
            else:
                raw_events = await _async_call(
                    hass,
                    TODO_DOMAIN,
                    "get_items",
                    {"entity_id": entity_id, "status": ["needs_action"]},
                    entity_id,
                )
        except (HomeAssistantError, vol.Invalid) as err:
            _LOGGER.debug("Reading %s failed: %s", entity_id, err)
            errors[entity_id] = str(err) or type(err).__name__
            continue
        for raw in raw_events:
            try:
                if domain == CALENDAR_DOMAIN:
                    events.append(parse_event(entity_id, raw, tz))
                elif (item := todo_item_event(entity_id, raw, tz)) and item.start < end:
                    # Overdue items are kept (the engine carries them to today).
                    events.append(item)
            except (KeyError, ValueError) as err:
                _LOGGER.debug("Skipping entry %s of %s: %s", raw, entity_id, err)
    return events, errors
