"""The "next event" is the next one that still needs something to be done."""

from __future__ import annotations

from datetime import date
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
import pytest

from custom_components.laeutwerk.manager import LaeutwerkManager

from .common import PHONE, WASTE, FakeCalendars, at, muell_rule, setup_integration, tick
from .ha_testing import async_mock_service

WED = date(2026, 11, 11)
FRI = date(2026, 11, 13)
NEXT = "sensor.laeutwerk_muell_naechster_termin"
STATE = "sensor.laeutwerk_muell"


@pytest.fixture(autouse=True)
def phone(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "notify", PHONE.split(".")[1])


async def start(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, when, **changes: Any
) -> LaeutwerkManager:
    """Biomüll today (Wednesday), Altpapier on Friday."""
    freezer.move_to(when)
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Bio", WED)
    calendars.add_all_day(WASTE, "Papier", FRI)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule(**changes))
    await hass.async_block_till_done()
    return manager


def next_titles(hass: HomeAssistant, manager: LaeutwerkManager) -> tuple:
    status = manager.status("muell")["next_event"]
    sensor = hass.states.get(NEXT)
    return (
        status["titles"] if status else None,
        sensor.attributes.get("title") if sensor else None,
        hass.states.get(STATE).attributes.get("next_event"),
    )


async def test_expired_event_is_not_next(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    # Live case from 11.11.: Biomüll today, expire event_day 12:00.
    manager = await start(hass, freezer, at(WED, 8, 0), expire="event_day 12:00")
    await tick(hass, freezer, at(WED, 11, 59))
    assert next_titles(hass, manager) == (["Bio"], "Bio", "2026-11-10T23:00:00+00:00")
    assert hass.states.get(NEXT).attributes["days_until"] == 0

    await tick(hass, freezer, at(WED, 12, 1))
    assert next_titles(hass, manager) == (
        ["Papier"],
        "Papier",
        "2026-11-12T23:00:00+00:00",
    )
    assert hass.states.get(NEXT).state == "2026-11-12T23:00:00+00:00"
    assert hass.states.get(NEXT).attributes["days_until"] == 2


async def test_acknowledged_event_is_not_next(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    manager = await start(hass, freezer, at(WED, 7, 0), expire="event_day 12:00")
    await manager.async_acknowledge("muell", reminder_id="muell__20261111")
    await hass.async_block_till_done()
    assert next_titles(hass, manager)[0] == ["Papier"]


async def test_default_expiry_keeps_event_until_its_end(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    manager = await start(hass, freezer, at(WED, 8, 0), expire="event_end")
    await tick(hass, freezer, at(WED, 23, 30))
    assert next_titles(hass, manager)[0] == ["Bio"]
    await tick(hass, freezer, at(date(2026, 11, 12), 0, 1))
    assert next_titles(hass, manager)[0] == ["Papier"]


async def test_overdue_todo_and_interval_stay_next_until_done(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(at(WED, 8, 0))
    hass.states.async_set("todo.aufgaben", "1")

    async def get_items(call: ServiceCall) -> dict[str, Any]:
        return {
            "todo.aufgaben": {
                "items": [
                    {"summary": "Steuer", "status": "needs_action", "due": "2026-11-02"}
                ]
            }
        }

    hass.services.async_register(
        "todo", "get_items", get_items, supports_response=SupportsResponse.ONLY
    )
    _, manager = await setup_integration(hass)
    common = {
        "reminders": [{"at": "09:00"}],
        "expire": "event_day 12:00",
        "signals": [],
    }
    await manager.async_create_rule(
        {"id": "todo", "name": "Aufgaben", "sources": ["todo.aufgaben"], **common}
    )
    await manager.async_create_rule(
        {
            "id": "filter",
            "name": "Filter",
            "interval": {"every": 30, "start": "2026-10-01"},
            **common,
        }
    )
    await hass.async_block_till_done()

    # After the expiry of today's reminder both stay the next event …
    await tick(hass, freezer, at(WED, 12, 1))
    for rule_id, title in (("todo", "Steuer"), ("filter", "Filter")):
        assert manager.status(rule_id)["next_event"]["titles"] == [title]
        assert manager.status(rule_id)["next_event"]["days_until"] == 0

    # … also the next day (a new reminder for the still open item) …
    thu = date(2026, 11, 12)
    await tick(hass, freezer, at(thu, 9, 0))
    assert manager.status("todo")["next_event"]["day"] == "2026-11-12"

    # … until they are acknowledged.
    await manager.async_acknowledge("todo", reminder_id="todo__20261112")
    await hass.async_block_till_done()
    assert manager.status("todo")["next_event"] is None
    await manager.async_acknowledge("filter", reminder_id="filter__20261112")
    await hass.async_block_till_done()
    assert manager.status("filter")["next_event"]["day"] == "2026-12-12"
