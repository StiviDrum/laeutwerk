"""Read events from calendar entities with the ``calendar.get_events`` action."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .compat import vol
from .matching import parse_event
from .model import CalendarEvent

_LOGGER = logging.getLogger(__name__)


async def async_fetch_events(
    hass: HomeAssistant, entity_ids: Iterable[str], start: datetime, end: datetime
) -> tuple[list[CalendarEvent], dict[str, str]]:
    """Return the events of some calendars and an error text per failed one."""
    tz = dt_util.get_default_time_zone()
    events: list[CalendarEvent] = []
    errors: dict[str, str] = {}
    for entity_id in entity_ids:
        if hass.states.get(entity_id) is None:
            errors[entity_id] = "calendar not found"
            continue
        try:
            response = await hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": entity_id,
                    "start_date_time": start.isoformat(),
                    "end_date_time": end.isoformat(),
                },
                blocking=True,
                return_response=True,
            )
        except (HomeAssistantError, vol.Invalid) as err:
            _LOGGER.debug("Reading %s failed: %s", entity_id, err)
            errors[entity_id] = str(err) or type(err).__name__
            continue
        raw_events = ((response or {}).get(entity_id) or {}).get("events", [])
        for raw in raw_events:  # type: ignore[union-attr]
            try:
                events.append(parse_event(entity_id, raw, tz))  # type: ignore[arg-type]
            except (KeyError, ValueError) as err:
                _LOGGER.debug("Skipping event %s of %s: %s", raw, entity_id, err)
    return events, errors
