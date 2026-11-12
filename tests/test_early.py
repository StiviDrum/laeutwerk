"""0.9.2: early acknowledge setting, early feedback, too_early response."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import Context, HomeAssistant, ServiceCall
import pytest

from custom_components.laeutwerk.const import DOMAIN
from custom_components.laeutwerk.manager import LaeutwerkManager

from .common import PHONE, WASTE, FakeCalendars, at, setup_integration, tick
from .ha_testing import async_mock_service
from .test_tag_variables import VARIABLE, tag_rule

MON = date(2026, 11, 16)
TUE = date(2026, 11, 17)
THU = date(2026, 11, 19)
DOOR = "binary_sensor.haustuer"


@pytest.fixture(autouse=True)
def phone_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "custom_components.laeutwerk.signals.person_notify_targets",
        lambda hass, person: [PHONE],
    )


@pytest.fixture
def pushes(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "notify", PHONE.split(".")[1])


async def start(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    acknowledge: list[dict[str, Any]] | None = None,
    **changes: Any,
) -> LaeutwerkManager:
    """Monday 09:00: Rest + Bio Tuesday (reminder Mon 17:00), Papier Thursday."""
    freezer.move_to(at(MON, 9))
    hass.states.async_set("person.anna", "home", {"friendly_name": "Anna"})
    hass.states.async_set("person.ben", "home", {"friendly_name": "Ben"})
    hass.states.async_set(DOOR, "off")
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Rest", TUE)
    calendars.add_all_day(WASTE, "Bio", TUE)
    calendars.add_all_day(WASTE, "Papier", THU)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(tag_rule(acknowledge or VARIABLE, **changes))
    await hass.async_block_till_done()
    return manager


def states(manager: LaeutwerkManager) -> dict[str, str]:
    return {r.id: r.state for r in manager.reminders["muell"].values()}


async def scan(hass: HomeAssistant, tag_id: str) -> None:
    hass.bus.async_fire("tag_scanned", {"tag_id": tag_id}, context=Context())
    await hass.async_block_till_done()


async def door(hass: HomeAssistant) -> None:
    hass.states.async_set(DOOR, "off")
    await hass.async_block_till_done()
    hass.states.async_set(DOOR, "on")
    await hass.async_block_till_done()
    await hass.async_block_till_done()


TRIGGER = [
    {"type": "trigger", "trigger": {"trigger": "state", "entity_id": DOOR, "to": "on"}}
]


@pytest.mark.parametrize(
    ("early", "tuesday", "thursday"),
    [
        ({"mode": "off"}, "planned", "planned"),
        ({"mode": "hours", "hours": 1}, "planned", "planned"),
        ({"mode": "hours", "hours": 24}, "done", "planned"),
        ({"mode": "always"}, "done", "planned"),
    ],
)
async def test_modes_service_and_trigger(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    early: dict[str, Any],
    tuesday: str,
    thursday: str,
) -> None:
    manager = await start(hass, freezer, TRIGGER, early=early)
    await manager.async_acknowledge("muell", by="Anna")
    assert states(manager) == {"muell__20261117": tuesday, "muell__20261119": thursday}

    manager = await start(hass, freezer, TRIGGER, early=early)
    await door(hass)
    assert states(manager)["muell__20261117"] == tuesday


@pytest.mark.parametrize(
    ("early", "tag", "expected"),
    [
        ({"mode": "off"}, "restmuelltonne", "planned"),
        ({"mode": "hours", "hours": 24}, "restmuelltonne", "done"),
        # Thursday's Papier is 56 h away.
        ({"mode": "hours", "hours": 24}, "altpapiertonne", "planned"),
        ({"mode": "always"}, "altpapiertonne", "done"),
    ],
)
async def test_modes_tag(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    early: dict[str, Any],
    tag: str,
    expected: str,
) -> None:
    manager = await start(hass, freezer, early=early)
    await scan(hass, tag)
    done = "muell__20261117" if tag == "restmuelltonne" else "muell__20261119"
    other = "muell__20261119" if tag == "restmuelltonne" else "muell__20261117"
    assert states(manager)[done] == expected
    # The tag never acknowledges another bin's reminder.
    assert states(manager)[other] == "planned"


async def test_explicit_reminder_follows_the_mode(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    manager = await start(hass, freezer, early={"mode": "hours", "hours": 24})
    await manager.async_acknowledge("muell", reminder_id="muell__20261119")
    assert states(manager)["muell__20261119"] == "planned"
    await manager.async_acknowledge("muell", reminder_id="muell__20261117")
    assert states(manager)["muell__20261117"] == "done"


async def test_early_ack_moves_the_interval(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(at(MON, 9))
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(
        {
            "id": "filter",
            "name": "Filter",
            "interval": {"every": 10, "start": "2026-11-17"},
            "reminders": [{"at": "09:00"}],
            "early": {"mode": "always"},
            "expire": "event_end",
        }
    )
    await hass.async_block_till_done()
    runner = manager.runners["filter"]
    assert [o.day for o in runner.upcoming] == [TUE]
    assert len(await manager.async_acknowledge("filter", by="Anna")) == 1
    await hass.async_block_till_done()
    assert [o.day for o in runner.upcoming] == [MON + timedelta(days=10)]


# ------------------------------------------------------------- early feedback

FEEDBACK = {"message": "{titel} erst {wann}, {person}", "clear_after": 10}


def texts(pushes: list[ServiceCall]) -> list[ServiceCall]:
    return [c for c in pushes if c.data["message"] != "clear_notification"]


async def test_feedback_to_person_then_clears(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    manager = await start(hass, freezer, early={"mode": "off"}, early_feedback=FEEDBACK)
    pushes.clear()
    assert not await manager.async_acknowledge("muell", by="Anna", person="person.anna")
    await hass.async_block_till_done()
    (push,) = texts(pushes)
    assert push.data["message"].endswith(", Anna")
    tag = push.data["data"]["tag"]
    assert tag == "laeutwerk_early_muell__20261117"
    await tick(hass, freezer, at(MON, 9, 0) + timedelta(seconds=11))
    assert pushes[-1].data["message"] == "clear_notification"
    assert pushes[-1].data["data"]["tag"] == tag


async def test_feedback_falls_back_to_assignee_or_nobody(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    manager = await start(
        hass,
        freezer,
        early={"mode": "off"},
        early_feedback=FEEDBACK,
        assignee={"persons": ["person.ben"]},
    )
    pushes.clear()
    await manager.async_acknowledge("muell")
    await hass.async_block_till_done()
    assert texts(pushes)[0].data["message"].endswith(", Ben")

    manager = await start(hass, freezer, early={"mode": "off"}, early_feedback=FEEDBACK)
    pushes.clear()
    await manager.async_acknowledge("muell")
    await hass.async_block_till_done()
    assert not texts(pushes)


async def test_no_feedback_without_setting_or_when_acknowledged(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    manager = await start(hass, freezer, early={"mode": "off"})
    pushes.clear()
    await manager.async_acknowledge("muell", by="Anna", person="person.anna")
    await hass.async_block_till_done()
    assert not texts(pushes)


async def test_tag_feedback_uses_the_tags_own_reminder(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    manager = await start(
        hass,
        freezer,
        early={"mode": "off"},
        early_feedback={"message": "{tonne}", "clear_after": 0},
        assignee={"persons": ["person.ben"]},
    )
    pushes.clear()
    await scan(hass, "altpapiertonne")
    assert [c.data["message"] for c in texts(pushes)] == ["Papiertonne"]
    assert texts(pushes)[0].data["data"]["tag"] == "laeutwerk_early_muell__20261119"
    assert manager.reminders["muell"]["muell__20261119"].state == "planned"


async def test_too_early_in_service_response(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    manager = await start(hass, freezer, early={"mode": "off"})
    result = await hass.services.async_call(
        DOMAIN, "acknowledge", {"rule": "muell"}, blocking=True, return_response=True
    )
    assert result["acknowledged"] == []
    assert result["too_early"] == "Bio und Rest ist erst morgen dran."

    await manager.async_update_rule(
        "muell",
        {**manager.rules["muell"].to_dict(), "early": {"mode": "always"}},
    )
    result = await hass.services.async_call(
        DOMAIN, "acknowledge", {"rule": "muell"}, blocking=True, return_response=True
    )
    assert len(result["acknowledged"]) == 1
    assert result["too_early"] is None
