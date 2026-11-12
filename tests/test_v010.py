"""0.10: time variables, repeat texts, every_stage, hooks, stage min_age, sensors."""

from __future__ import annotations

from datetime import UTC, date
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest

from custom_components.laeutwerk.compat import vol
from custom_components.laeutwerk.manager import LaeutwerkManager
from custom_components.laeutwerk.matching import describe_since
from custom_components.laeutwerk.schema import validate_rule
from custom_components.laeutwerk.sensor import WaitingSinceSensor

from .common import PHONE, WASTE, FakeCalendars, at, muell_rule, setup_integration, tick
from .ha_testing import async_mock_service

MON = date(2026, 11, 16)
BELL = "binary_sensor.klingel"


def bell_rule(**changes: Any) -> dict[str, Any]:
    return {
        "id": "klingel",
        "name": "Klingel",
        "start_triggers": [{"trigger": "state", "entity_id": BELL, "to": "on"}],
        "expire": "+40h",
        "signals": [
            {"id": "push", "type": "notify", "targets": [PHONE], "message": "{titel}"}
        ],
        **changes,
    }


def push(**extra: Any) -> dict[str, Any]:
    return {"id": "push", "type": "notify", "targets": [PHONE], **extra}


@pytest.fixture
def pushes(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "notify", PHONE.split(".")[1])


def sent(pushes: list[ServiceCall]) -> list[str]:
    return [
        c.data["message"] for c in pushes if c.data["message"] != "clear_notification"
    ]


async def ring(hass: HomeAssistant) -> None:
    hass.states.async_set(BELL, "off")
    await hass.async_block_till_done()
    hass.states.async_set(BELL, "on")
    await hass.async_block_till_done()
    await hass.async_block_till_done()


async def start(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, when, **changes: Any
) -> LaeutwerkManager:
    freezer.move_to(when)
    hass.states.async_set(BELL, "off")
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(bell_rule(**changes))
    await hass.async_block_till_done()
    return manager


def test_describe_since() -> None:
    de = {
        0: "seit weniger als einer Minute",
        1: "seit 1 Minute",
        25: "seit 25 Minuten",
        60: "seit 1 Std.",
        85: "seit 1 Std. 25 Min.",
        120: "seit 2 Std.",
        1440: "seit 1 Tag",
        1620: "seit 1 Tag 3 Std.",
        2880: "seit 2 Tagen",
    }
    en = {
        0: "for less than a minute",
        1: "for 1 minute",
        25: "for 25 minutes",
        60: "for 1 h",
        85: "for 1 h 25 min",
        1620: "for 1 day 3 h",
        2880: "for 2 days",
    }
    assert {m: describe_since(m, "de") for m in de} == de
    assert {m: describe_since(m, "en") for m in en} == en


async def test_time_variables_nr_and_repeat_texts(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    manager = await start(
        hass,
        freezer,
        at(MON, 9),
        repeat={"every": 60, "max": 5},
        signals=[push(message="{nr}|{seit}|{seit_min}|{erinnert_um}")],
    )
    reminder_vars = manager.runners["klingel"].variables
    await ring(hass)
    assert sent(pushes) == ["1|seit weniger als einer Minute|0|09:00"]
    await tick(hass, freezer, at(MON, 10))
    assert sent(pushes)[-1] == "2|seit 1 Std.|60|09:00"
    await manager.async_snooze(10)
    await tick(hass, freezer, at(MON, 10, 10))
    assert sent(pushes)[-1] == "3|seit 1 Std. 10 Min.|70|09:00"
    reminder = manager.reminders["klingel"]
    assert next(iter(reminder.values())).nr == 3
    assert reminder_vars(next(iter(reminder.values())))["seit_min"] == "70"


async def test_variables_before_first_remind(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", date(2026, 11, 17))
    freezer.move_to(at(MON, 9))
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await hass.async_block_till_done()
    runner = manager.runners["muell"]
    reminder = manager.reminders["muell"]["muell__20261117"]
    for item in (reminder, runner.next_occurrence()):
        variables = runner.variables(item)
        assert variables["seit"] == variables["erinnert_um"] == ""
        assert (variables["seit_min"], variables["nr"]) == ("0", "1")


async def test_hooks_and_failing_hook(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    hooks = async_mock_service(hass, "test", "hook")

    async def boom(call: ServiceCall) -> None:
        raise HomeAssistantError("boom")

    hass.services.async_register("test", "boom", boom)
    data = {"nr": "{{ nr }}", "rid": "{{ rule_id }}", "min": "{{ seit_min }}"}
    manager = await start(
        hass,
        freezer,
        at(MON, 9),
        repeat={"every": 30, "max": 5},
        expire="+2h",
        on_reminded=[{"action": "test.hook", "data": {"kind": "rem", **data}}],
        on_missed=[{"action": "test.hook", "data": {"kind": "miss", **data}}],
    )
    await ring(hass)
    await tick(hass, freezer, at(MON, 9, 30))
    assert [(c.data["kind"], str(c.data["nr"])) for c in hooks] == [
        ("rem", "1"),
        ("rem", "2"),
    ]
    assert hooks[1].data["rid"] == "klingel"
    assert str(hooks[1].data["min"]) == "30"
    await tick(hass, freezer, at(MON, 11, 1))
    assert hooks[-1].data["kind"] == "miss"
    assert manager.runners["klingel"].state == "missed"
    # A failing hook blocks neither signals nor state.
    await manager.async_create_rule(
        bell_rule(id="b2", name="B2", on_reminded=[{"action": "test.boom"}])
    )
    await hass.async_block_till_done()
    before = len(sent(pushes))
    await manager.async_acknowledge("klingel")
    freezer.move_to(at(MON, 12))
    await ring(hass)
    assert len(sent(pushes)) > before
    assert manager.runners["b2"].state == "reminded"


async def test_stage_clock_time_is_next_occurrence(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    manager = await start(
        hass,
        freezer,
        at(MON, 19, 40),
        escalation=[{"after": "10:00"}],
        signals=[
            push(message="x", send_on="first"),
            push(id="s", message="s1", send_on="stage", stage=1, stage_repeat=True),
        ],
    )
    freezer.move_to(at(MON, 19, 42))
    await ring(hass)
    reminder = next(iter(manager.reminders["klingel"].values()))
    await tick(hass, freezer, at(MON, 23, 59))
    assert reminder.stage == 0
    await tick(hass, freezer, at(date(2026, 11, 17), 9, 59))
    assert reminder.stage == 0
    await tick(hass, freezer, at(date(2026, 11, 17), 10, 0))
    assert reminder.stage == 1
    assert sent(pushes) == ["x", "s1"]


async def test_stage_next_morning_across_dst(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    sat, sun = date(2026, 10, 24), date(2026, 10, 25)
    manager = await start(
        hass,
        freezer,
        at(sat, 23, 30),
        escalation=[{"after": "10:00"}],
        signals=[push(message="x")],
    )
    await ring(hass)
    reminder = next(iter(manager.reminders["klingel"].values()))
    await tick(hass, freezer, at(sun, 9, 59))
    assert reminder.stage == 0
    await tick(hass, freezer, at(sun, 10, 0))
    assert reminder.stage == 1


async def test_stage_min_age_skips(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    manager = await start(
        hass,
        freezer,
        at(MON, 19, 42),
        escalation=[{"after": "21:30", "min_age": "2h"}, {"after": "4h"}],
        signals=[
            push(message="x", send_on="first"),
            push(id="s1", message="s1", send_on="stage", stage=1),
        ],
    )
    await ring(hass)
    reminder = next(iter(manager.reminders["klingel"].values()))
    await tick(hass, freezer, at(MON, 21, 30))
    assert reminder.stage == 1  # skipped silently
    assert reminder.nr == 1
    assert sent(pushes) == ["x"]
    await tick(hass, freezer, at(MON, 23, 42))
    assert reminder.stage == 2
    assert reminder.nr == 2


async def test_calendar_stage_same_evening(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", date(2026, 11, 17))
    freezer.move_to(at(MON, 9))
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(
        muell_rule(escalation=[{"after": "21:30"}], signals=[push(message="x")])
    )
    await hass.async_block_till_done()
    await tick(hass, freezer, at(MON, 17))
    reminder = manager.reminders["muell"]["muell__20261117"]
    await tick(hass, freezer, at(MON, 21, 30))
    assert reminder.stage == 1
    assert reminder.nr == 2


async def test_sensor_attributes_and_waiting_since(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    manager = await start(hass, freezer, at(MON, 9))
    waiting = WaitingSinceSensor(manager, "klingel")
    assert waiting.native_value is None
    await ring(hass)
    state = hass.states.get("sensor.laeutwerk_klingel")
    assert state.attributes["reminded_at"] == at(MON, 9).astimezone(UTC).isoformat()
    assert state.attributes["repeats"] == 0
    assert state.attributes["finished_at"] is None
    assert state.attributes["last_reminded_at"] is not None
    assert waiting.native_value == at(MON, 9)
    entry = er.async_get(hass).async_get("sensor.laeutwerk_klingel_wartet_seit")
    assert entry is not None
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    await manager.async_snooze(30)
    assert waiting.native_value == at(MON, 9)
    await manager.async_acknowledge("klingel")
    assert waiting.native_value is None
    state = hass.states.get("sensor.laeutwerk_klingel")
    assert state.attributes["finished_at"] is not None
    reminder = next(iter(manager.reminders["klingel"].values()))
    assert manager.reminder_payload("klingel", reminder)["nr"] == 1


def test_schema() -> None:
    base = {
        "id": "r",
        "name": "R",
        "start_triggers": [{"trigger": "state", "entity_id": BELL, "to": "on"}],
    }
    ok = validate_rule(
        {
            **base,
            "escalation": [{"after": "21:30", "min_age": "2h"}],
            "signals": [push(message="m")],
            "on_missed": [{"action": "test.hook"}],
        }
    )
    assert ok["on_reminded"] == []
    with pytest.raises(vol.Invalid):
        validate_rule({**base, "escalation": [{"after": "1h", "min_age": "soon"}]})
