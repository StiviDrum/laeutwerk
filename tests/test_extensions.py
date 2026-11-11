"""0.6 extensions: more sources, interval, activation, on_done, assignee, escalation."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
import pytest

from custom_components.laeutwerk.compat import vol
from custom_components.laeutwerk.manager import LaeutwerkManager
from custom_components.laeutwerk.schema import validate_rule

from .common import PHONE, WASTE, FakeCalendars, at, muell_rule, setup_integration, tick
from .ha_testing import async_mock_service

MON = date(2026, 11, 16)
TUE = date(2026, 11, 17)


def push(**extra: Any) -> dict[str, Any]:
    return {
        "id": "push",
        "type": "notify",
        "targets": [PHONE],
        "message": "{titel}",
        **extra,
    }


@pytest.fixture
def pushes(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "notify", PHONE.split(".")[1])


def messages(calls: list[ServiceCall]) -> list[str]:
    return [
        c.data["message"] for c in calls if c.data["message"] != "clear_notification"
    ]


def simple_rule(**changes: Any) -> dict[str, Any]:
    """A rule without keywords that reminds on the day at 09:00."""
    return {
        "id": "r",
        "name": "Filter tauschen",
        "sources": [],
        "reminders": [{"at": "09:00"}],
        "signals": [push()],
        **changes,
    }


async def start(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, when, rule: dict[str, Any]
) -> LaeutwerkManager:
    freezer.move_to(when)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(rule)
    await hass.async_block_till_done()
    return manager


# ------------------------------------------------------------------- sources


async def test_date_entities_as_sources(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    hass.states.async_set("date.tuev", "2026-11-17", {"friendly_name": "TÜV Auto"})
    hass.states.async_set(
        "sensor.abholung",
        "2026-11-18T05:30:00+00:00",
        {"friendly_name": "Abholung", "device_class": "timestamp"},
    )
    hass.states.async_set(
        "input_datetime.arzt",
        "2026-11-19 10:15:00",
        {"friendly_name": "Arzt", "has_date": True, "has_time": True},
    )
    hass.states.async_set(
        "input_datetime.wecker", "06:30:00", {"has_date": False, "has_time": True}
    )
    hass.states.async_set("datetime.leer", "unknown")
    sources = [
        "date.tuev",
        "sensor.abholung",
        "input_datetime.arzt",
        "input_datetime.wecker",
        "datetime.leer",
    ]
    manager = await start(
        hass,
        freezer,
        at(MON, 7),
        simple_rule(sources=sources, bundle=False, reminders=[{"at": "-1d 20:00"}]),
    )
    runner = manager.runners["r"]
    assert [(o.events[0].summary, o.events[0].all_day) for o in runner.upcoming] == [
        ("TÜV Auto", True),
        ("Abholung", False),
        ("Arzt", False),
    ]
    assert runner.variables(runner.upcoming[2])["uhrzeit"] == "10:15"
    assert runner.errors == {}

    # The date changes: the reminder follows.
    hass.states.async_set("date.tuev", "2026-11-24", {"friendly_name": "TÜV Auto"})
    await tick(hass, freezer, at(MON, 7, 1))
    assert runner.upcoming[-1].events[0].summary == "TÜV Auto"
    await tick(hass, freezer, at(MON, 20, 0))
    assert messages(pushes) == []
    await tick(hass, freezer, at(TUE, 20, 0))
    assert messages(pushes) == ["Abholung"]


async def test_todo_items_with_due_date(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    items = [
        {
            "summary": "Rezept abholen",
            "uid": "1",
            "status": "needs_action",
            "due": "2026-11-17",
        },
        {"summary": "Ohne Datum", "uid": "2", "status": "needs_action"},
        {
            "summary": "Steuer",
            "uid": "3",
            "status": "needs_action",
            "due": "2026-11-12",  # overdue
            "description": "Belege",
        },
    ]
    hass.states.async_set("todo.aufgaben", "2", {"friendly_name": "Aufgaben"})

    async def get_items(call: ServiceCall) -> dict[str, Any]:
        assert call.data["status"] == ["needs_action"]
        return {"todo.aufgaben": {"items": items}}

    hass.services.async_register(
        "todo", "get_items", get_items, supports_response=SupportsResponse.ONLY
    )
    manager = await start(
        hass, freezer, at(MON, 7), simple_rule(sources=["todo.aufgaben"], bundle=False)
    )
    runner = manager.runners["r"]
    # The overdue item is due today, so it reminds at 09:00 today.
    assert [(o.events[0].summary, o.day) for o in runner.upcoming] == [
        ("Steuer", MON),
        ("Rezept abholen", TUE),
    ]
    assert runner.variables(runner.upcoming[0])["beschreibung"] == "Belege"
    await tick(hass, freezer, at(MON, 9, 0))
    assert messages(pushes) == ["Steuer"]
    # Still open the next day: reminded again (daily until done).
    await tick(hass, freezer, at(TUE, 9, 0))
    assert sorted(messages(pushes)) == ["Rezept abholen", "Steuer", "Steuer"]


def test_source_validation() -> None:
    validate_rule(simple_rule(sources=["todo.x", "date.y", "sensor.z", "calendar.a"]))
    with pytest.raises(vol.Invalid, match="cannot be a source"):
        validate_rule(simple_rule(sources=["light.lampe"]))
    with pytest.raises(vol.Invalid, match="source or an 'interval'"):
        validate_rule(simple_rule())


# ------------------------------------------------------------------ interval


async def test_interval_since_done(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    rule = simple_rule(interval={"every": "2w"}, expire="event_end")
    manager = await start(hass, freezer, at(MON, 7), rule)
    stored = manager.rules["r"]
    assert stored.interval == {"every": 14, "start": "2026-11-16"}
    runner = manager.runners["r"]
    assert [(o.events[0].summary, o.day) for o in runner.upcoming] == [
        ("Filter tauschen", MON)
    ]

    await tick(hass, freezer, at(MON, 9, 0))
    assert messages(pushes) == ["Filter tauschen"]
    # Not done today: due again tomorrow (daily until done).
    await tick(hass, freezer, at(TUE, 9, 0))
    assert manager.history["r"][0]["state"] == "missed"
    assert messages(pushes) == ["Filter tauschen"] * 2

    await manager.async_acknowledge("r", by="Steven")
    await hass.async_block_till_done()
    assert [o.day for o in runner.upcoming] == [TUE + timedelta(days=14)]
    await tick(hass, freezer, at(TUE + timedelta(days=13), 9, 0))
    assert len(messages(pushes)) == 2
    await tick(hass, freezer, at(TUE + timedelta(days=14), 9, 0))
    assert len(messages(pushes)) == 3

    # Changing the rule keeps the start; the history decides the next day.
    await manager.async_update_rule("r", {**rule, "name": "Filter"})
    assert manager.rules["r"].interval["start"] == "2026-11-16"


async def test_interval_with_start(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    manager = await start(
        hass,
        freezer,
        at(MON, 7),
        simple_rule(interval={"every": 90, "start": "2026-12-01"}),
    )
    # Shown as the next event even beyond the 14 days of calendar look-ahead.
    assert [o.day for o in manager.runners["r"].upcoming] == [date(2026, 12, 1)]
    assert [r.state for r in manager.reminders["r"].values()] == ["planned"]
    with pytest.raises(vol.Invalid):
        validate_rule(simple_rule(interval={"every": "0d"}))


# ---------------------------------------------------------------- activation


async def test_activation_conditions(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    hass.states.async_set("input_boolean.urlaub", "on")
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", TUE)
    rule = muell_rule(
        activation={
            "conditions": [
                {
                    "condition": "state",
                    "entity_id": "input_boolean.urlaub",
                    "state": "off",
                }
            ]
        }
    )
    manager = await start(hass, freezer, at(MON, 9), rule)
    assert manager.status("muell")["active"] is False
    assert manager.status("muell")["state"] == "inactive"
    assert manager.reminders["muell"] == {}

    # Back from vacation: the rule follows the condition entity at once.
    hass.states.async_set("input_boolean.urlaub", "off")
    await tick(hass, freezer, at(MON, 9, 1))
    assert manager.status("muell")["active"] is True
    assert manager.status("muell")["state"] == "planned"
    await tick(hass, freezer, at(MON, 17, 0))
    assert len(messages(pushes)) == 1


async def test_season(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    calendars = FakeCalendars(hass, WASTE)
    for day in (date(2026, 11, 30), date(2026, 12, 1), date(2026, 12, 2)):
        calendars.add_all_day(WASTE, "Bio", day)
    winter_off = {"season": {"from": "04-01", "to": "11-30"}}
    manager = await start(
        hass, freezer, at(date(2026, 11, 25), 9), muell_rule(activation=winter_off)
    )
    assert [o.day for o in manager.runners["muell"].upcoming] == [date(2026, 11, 30)]

    across_new_year = {"season": {"from": "12-01", "to": "02-28"}}
    await manager.async_update_rule("muell", muell_rule(activation=across_new_year))
    await hass.async_block_till_done()
    assert [o.day for o in manager.runners["muell"].upcoming] == [
        date(2026, 12, 1),
        date(2026, 12, 2),
    ]
    with pytest.raises(vol.Invalid, match="month-day"):
        validate_rule(
            muell_rule(activation={"season": {"from": "4.1.", "to": "11-30"}})
        )
    with pytest.raises(vol.Invalid, match="valid day"):
        validate_rule(
            muell_rule(activation={"season": {"from": "02-30", "to": "11-30"}})
        )


# ------------------------------------------------------------------- on_done


async def test_actions_when_done(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    calls = async_mock_service(hass, "test", "done")
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", TUE)
    rule = muell_rule(
        on_done=[
            {
                "action": "test.done",
                "data": {"text": "{{ person }}: {{ tonne }} via {{ via }}"},
            }
        ]
    )
    manager = await start(hass, freezer, at(MON, 9), rule)
    await tick(hass, freezer, at(MON, 17, 0))
    await manager.async_acknowledge("muell", by="Steven", via="tag")
    await hass.async_block_till_done()
    assert [c.data["text"] for c in calls] == ["Steven: Papiertonne via tag"]

    with pytest.raises(vol.Invalid, match="on_done"):
        await manager.async_update_rule(
            "muell", muell_rule(on_done=[{"action": "kein dienst"}])
        )


# ------------------------------------------------------------------ assignee


async def test_assignee_rotation_and_audience(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    hass.states.async_set("person.steven", "home", {"friendly_name": "Steven"})
    hass.states.async_set("person.anna", "home", {"friendly_name": "Anna"})
    calendars = FakeCalendars(hass, WASTE)
    for day in (TUE, date(2026, 11, 24), date(2026, 11, 25)):
        calendars.add_all_day(WASTE, "Papier", day)
    persons = ["person.steven", "person.anna"]

    def rule(rotation: str) -> dict[str, Any]:
        return muell_rule(
            assignee={"persons": persons, "rotation": rotation},
            signals=[
                push(
                    message="{zustaendig}: {tonne}",
                    targets=[PHONE],
                    audience="assignee",
                )
            ],
        )

    manager = await start(hass, freezer, at(MON, 9), rule("per_event"))
    reminders = sorted(manager.reminders["muell"].values(), key=lambda r: r.start)
    assert [r.assignee for r in reminders] == [
        "person.steven",
        "person.anna",
        "person.steven",
    ]
    await tick(hass, freezer, at(MON, 17, 0))
    assert messages(pushes) == ["Steven: Papiertonne"]
    assert manager.status("muell")["reminders"][0]["assignee_name"] == "Steven"

    # Weekly: by calendar week of the event day.
    await manager.async_delete_rule("muell")
    manager2 = await _recreate(hass, manager, rule("weekly"))
    weekly = sorted(manager2.reminders["muell"].values(), key=lambda r: r.start)
    assert weekly[1].assignee == weekly[2].assignee != weekly[0].assignee

    # After the last one who did it.
    await manager.async_delete_rule("muell")
    manager.history["muell"] = [
        {"state": "done", "acknowledged_by": "Steven"},
        {"state": "done", "acknowledged_by": "Anna"},
        {"state": "done", "acknowledged_by": "Steven"},
    ]
    await manager.async_create_rule(rule("after_last"))
    await hass.async_block_till_done()
    assert {r.assignee for r in manager.reminders["muell"].values()} == {"person.anna"}
    assert manager.status("muell")["assignee_stats"] == {"Steven": 2, "Anna": 1}

    with pytest.raises(vol.Invalid, match="audience 'assignee' needs"):
        validate_rule(muell_rule(signals=[push(audience="assignee")]))


async def _recreate(
    hass: HomeAssistant, manager: LaeutwerkManager, rule: dict[str, Any]
) -> LaeutwerkManager:
    await manager.async_create_rule(rule)
    await hass.async_block_till_done()
    return manager


# ---------------------------------------------------------------- escalation


async def test_escalation_stages(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    """17:00 push → from 19:00 the lamp counts → 21:30 announcement."""
    hass.states.async_set("light.stehleuchte", "off")
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", TUE)
    rule = muell_rule(
        escalation=[{"after": "2h"}, {"after": "21:30"}],
        signals=[
            push(id="push", message="stufe 0"),
            push(
                id="lampe",
                message="lampe",
                stage=1,
                when={
                    "opportunity": {
                        "trigger": "state",
                        "entity_id": "light.stehleuchte",
                        "to": "on",
                    }
                },
            ),
            push(id="ansage", message="stufe 2", stage=2),
        ],
    )
    manager = await start(hass, freezer, at(MON, 9), rule)
    await tick(hass, freezer, at(MON, 17, 0))
    assert messages(pushes) == ["stufe 0"]

    async def lamp() -> None:
        hass.states.async_set("light.stehleuchte", "off")
        await hass.async_block_till_done()
        hass.states.async_set("light.stehleuchte", "on")
        await hass.async_block_till_done()
        await hass.async_block_till_done()

    await lamp()  # stage 0: the lamp does not count yet
    assert messages(pushes) == ["stufe 0"]

    await tick(hass, freezer, at(MON, 19, 0))
    reminder = manager.reminders["muell"]["muell__20261117"]
    assert reminder.stage == 1
    await lamp()
    assert messages(pushes) == ["stufe 0", "lampe"]

    await tick(hass, freezer, at(MON, 21, 29))
    assert reminder.stage == 1
    await tick(hass, freezer, at(MON, 21, 30))
    assert reminder.stage == 2
    assert messages(pushes) == ["stufe 0", "lampe", "stufe 2"]
    # Acknowledged: no further stages.
    await manager.async_acknowledge("muell")
    await tick(hass, freezer, at(TUE, 8, 0))
    assert len(messages(pushes)) == 3

    with pytest.raises(vol.Invalid, match="stage 3 does not exist"):
        validate_rule(muell_rule(escalation=[{"after": "1h"}], signals=[push(stage=3)]))
    with pytest.raises(vol.Invalid, match="invalid escalation time"):
        validate_rule(muell_rule(escalation=[{"after": "bald"}]))


def test_escalation_stage_colors() -> None:
    rule = validate_rule(
        muell_rule(escalation=[{"after": "2h", "color": "#FFB020"}, {"after": "21:30"}])
    )
    assert rule["escalation"] == [
        {"after": "2h", "color": "#ffb020"},
        {"after": "21:30"},
    ]
    with pytest.raises(vol.Invalid, match="not a colour"):
        validate_rule(muell_rule(escalation=[{"after": "2h", "color": "orange"}]))
