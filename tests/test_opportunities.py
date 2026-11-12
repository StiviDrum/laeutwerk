"""Opportunities, manual operation, repeat, snooze and ways to acknowledge."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import Context, HomeAssistant, ServiceCall
import pytest

from custom_components.laeutwerk.manager import LaeutwerkManager
from custom_components.laeutwerk.triggers import own_context

from .common import PHONE, WASTE, FakeCalendars, at, muell_rule, setup_integration, tick
from .ha_testing import async_mock_service

MON = date(2026, 11, 16)
TUE = date(2026, 11, 17)
LAMP = "light.stehleuchte"
DOOR = "binary_sensor.haustuer"
REMINDER = "muell__20261117"


def lamp_on(**extra: Any) -> dict[str, Any]:
    return {
        "opportunity": {"trigger": "state", "entity_id": LAMP, "to": "on"},
        **extra,
    }


def push(when: Any = "now", **extra: Any) -> dict[str, Any]:
    return {
        "id": "push",
        "type": "notify",
        "targets": [PHONE],
        "message": "{tonnen}",
        "when": when,
        **extra,
    }


@pytest.fixture
def pushes(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "notify", PHONE.split(".")[1])


def messages(pushes: list[ServiceCall]) -> list[str]:
    return [call.data["message"] for call in pushes]


async def start(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, **changes: Any
) -> LaeutwerkManager:
    """Monday 09:00, Papier on Tuesday, reminder Monday 17:00."""
    freezer.move_to(at(MON, 9))
    hass.states.async_set(LAMP, "off")
    hass.states.async_set(DOOR, "off")
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", TUE)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule(**changes))
    await hass.async_block_till_done()
    return manager


async def switch(
    hass: HomeAssistant, entity_id: str, state: str, context: Context | None = None
) -> None:
    hass.states.async_set(entity_id, state, context=context)
    await hass.async_block_till_done()
    await hass.async_block_till_done()


async def toggle_lamp(hass: HomeAssistant, context: Context | None = None) -> None:
    await switch(hass, LAMP, "off")
    await switch(hass, LAMP, "on", context)


# --------------------------------------------------------------- opportunities


async def test_opportunity_only_between_reminder_and_acknowledge(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    manager = await start(hass, freezer, signals=[push(lamp_on())])
    runner = manager.runners["muell"]
    listener = runner._opportunities[0]

    # Planned: the trigger is not even attached.
    assert not listener.active
    await toggle_lamp(hass)
    assert not pushes

    # Reminder time: nothing is sent by itself ...
    await tick(hass, freezer, at(MON, 17, 0))
    assert manager.status("muell")["state"] == "reminded"
    assert not pushes
    assert listener.active
    # ... but at every opportunity.
    await toggle_lamp(hass)
    await toggle_lamp(hass)
    assert messages(pushes) == ["Papiertonne", "Papiertonne"]
    assert manager.reminders["muell"][REMINDER].signals_sent == {"push": 2}

    await manager.async_acknowledge("muell")
    await hass.async_block_till_done()
    assert not listener.active
    sent = len(pushes)
    await toggle_lamp(hass)
    assert len(pushes) == sent


async def test_opportunity_respects_limit_and_quiet_time(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    await start(
        hass,
        freezer,
        signals=[
            push(
                lamp_on(),
                limit={"per_reminder": 1},
                quiet=[{"from": "00:00", "to": "10:00", "mode": "skip"}],
            )
        ],
        expire="event_end",
    )
    await tick(hass, freezer, at(MON, 17, 0))
    await tick(hass, freezer, at(TUE, 7, 0))
    await toggle_lamp(hass)  # light alarm clock time: quiet
    assert not pushes
    await tick(hass, freezer, at(TUE, 10, 0))
    await toggle_lamp(hass)
    await toggle_lamp(hass)  # at most once per reminder
    assert messages(pushes) == ["Papiertonne"]


async def test_manual_only_ignores_automations_and_own_signals(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    await start(
        hass,
        freezer,
        signals=[
            push(lamp_on(manual_only=True), id="manual", message="manual"),
            push(lamp_on(), id="always", message="always"),
        ],
    )
    await tick(hass, freezer, at(MON, 17, 0))

    # An automation or script (e.g. the light alarm clock): context has a parent.
    await toggle_lamp(hass, Context(parent_id="01AUTOMATION"))
    assert messages(pushes) == ["always"]

    # Läutwerk's own light signal is never an opportunity.
    await toggle_lamp(hass, own_context())
    await toggle_lamp(hass, Context(parent_id=own_context().id))
    assert messages(pushes) == ["always"]

    # Wall switch (no user) and dashboard (user) are real operation.
    await toggle_lamp(hass)
    await toggle_lamp(hass, Context(user_id="someone"))
    assert sorted(messages(pushes)[1:]) == ["always", "always", "manual", "manual"]


async def test_person_variable(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    pushes: list[ServiceCall],
    hass_admin_user,
) -> None:
    hass.states.async_set(
        "person.steven",
        "not_home",
        {"friendly_name": "Steven", "user_id": hass_admin_user.id},
    )
    hass.states.async_set("person.anna", "not_home", {"friendly_name": "Anna"})
    comes_home = {
        "opportunity": {
            "trigger": "state",
            "entity_id": ["person.steven", "person.anna"],
            "to": "home",
        }
    }
    await start(
        hass,
        freezer,
        signals=[
            push(comes_home, id="heim", message="Hallo {person}!"),
            push(lamp_on(), id="lampe", message="Lampe: {person}."),
            push(id="sofort", message="Sofort: {person}."),
        ],
    )
    await tick(hass, freezer, at(MON, 17, 0))
    assert messages(pushes) == ["Sofort: ."]

    hass.states.async_set("person.anna", "home", {"friendly_name": "Anna"})
    await hass.async_block_till_done()
    await toggle_lamp(hass, Context(user_id=hass_admin_user.id))
    await toggle_lamp(hass)
    assert messages(pushes)[1:] == ["Hallo Anna!", "Lampe: Steven.", "Lampe: ."]


async def test_invalid_opportunity_is_refused(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    manager = await start(hass, freezer)
    for when in (
        "later",
        {"opportunity": []},
        {"opportunity": {"trigger": "gibt_es_nicht"}},
        {"opportunity": {"trigger": "state"}},
        {"manual_only": True},
    ):
        with pytest.raises(Exception):  # noqa: B017
            await manager.async_update_rule("muell", muell_rule(signals=[push(when)]))


# ----------------------------------------------------------------------- repeat


async def test_repeat_until_acknowledged_with_maximum(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    freezer.move_to(at(MON, 9))
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", TUE)
    calendars.add_all_day(WASTE, "Bio", date(2026, 11, 24))
    entry, manager = await setup_integration(hass)
    await manager.async_create_rule(
        muell_rule(signals=[push()], repeat={"every": "1h", "max": 2})
    )
    assert manager.rules["muell"].repeat == {"every": 60, "max": 2}

    await tick(hass, freezer, at(MON, 17, 0))
    await tick(hass, freezer, at(MON, 17, 59))
    assert len(pushes) == 1
    await tick(hass, freezer, at(MON, 18, 0))
    assert len(pushes) == 2

    # A restart in between neither repeats early nor forgets the count.
    assert await hass.config_entries.async_unload(entry.entry_id)
    freezer.move_to(at(MON, 18, 30))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    manager = entry.runtime_data
    assert len(pushes) == 2
    await tick(hass, freezer, at(MON, 19, 0))
    assert len(pushes) == 3
    await tick(hass, freezer, at(MON, 20, 0))
    await tick(hass, freezer, at(MON, 22, 0))
    assert messages(pushes) == ["Papiertonne"] * 3  # maximum reached

    # Next week: acknowledging stops the repetition.
    await tick(hass, freezer, at(date(2026, 11, 23), 17, 0))
    await tick(hass, freezer, at(date(2026, 11, 23), 18, 0))
    await manager.async_acknowledge("muell")
    await tick(hass, freezer, at(date(2026, 11, 23), 19, 0))
    assert [m for m in messages(pushes) if m == "Biotonne"] == ["Biotonne"] * 2


# ----------------------------------------------------------------------- snooze


async def test_snooze_service(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    manager = await start(
        hass,
        freezer,
        signals=[push()],
        reminders=[{"at": "-1d 17:00"}, {"at": "-1d 18:00"}],
    )
    await tick(hass, freezer, at(MON, 17, 0))
    await tick(hass, freezer, at(MON, 17, 5))

    result = await hass.services.async_call(
        "laeutwerk", "snooze", {"duration": "3h"}, blocking=True, return_response=True
    )
    await hass.async_block_till_done()
    assert result == {"snoozed": [REMINDER]}
    assert manager.status("muell")["state"] == "planned"
    assert hass.states.get("binary_sensor.laeutwerk_muell_offen").state == "off"
    assert messages(pushes) == ["Papiertonne", "clear_notification"]

    # The regular 18:00 reminder is skipped while snoozed.
    await tick(hass, freezer, at(MON, 18, 0))
    await tick(hass, freezer, at(MON, 20, 4))
    assert len(pushes) == 2
    await tick(hass, freezer, at(MON, 20, 5))
    assert manager.status("muell")["state"] == "reminded"
    assert messages(pushes)[2:] == ["Papiertonne"]
    await tick(hass, freezer, at(MON, 23, 0))
    assert len(pushes) == 3

    # Nothing open -> nothing snoozed.
    await manager.async_acknowledge("muell")
    assert await manager.async_snooze(30) == []


async def test_snooze_from_push_button_and_acknowledge_while_snoozed(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    buttons = [
        {"ack": True, "label": "Steht draußen"},
        {"snooze": "90m", "label": "Später"},
    ]
    manager = await start(hass, freezer, signals=[push(actions=buttons)])
    await tick(hass, freezer, at(MON, 17, 0))
    assert pushes[0].data["data"]["actions"] == [
        {"action": f"LAEUTWERK_ACK__{REMINDER}", "title": "Steht draußen"},
        {"action": f"LAEUTWERK_SNOOZE__90__{REMINDER}", "title": "Später"},
    ]

    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": f"LAEUTWERK_SNOOZE__90__{REMINDER}"},
    )
    await hass.async_block_till_done()
    reminder = manager.reminders["muell"][REMINDER]
    assert reminder.state == "planned"
    assert reminder.snoozed_until == at(MON, 18, 30)

    # "Done" also works while snoozed; then nothing comes back.
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.laeutwerk_muell_erledigt"},
        blocking=True,
    )
    await tick(hass, freezer, at(MON, 18, 30))
    assert reminder.state == "done"
    assert messages(pushes) == ["Papiertonne", "clear_notification"]


async def test_snoozed_reminder_expires(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    manager = await start(hass, freezer, signals=[push()])
    await tick(hass, freezer, at(MON, 17, 0))
    await manager.async_snooze(24 * 60, "muell")
    await tick(hass, freezer, at(TUE, 12, 0))
    assert manager.status("muell")["state"] == "missed"
    await tick(hass, freezer, at(TUE, 17, 0))
    assert messages(pushes).count("Papiertonne") == 1


# ------------------------------------------------------------------ acknowledge


async def test_acknowledge_by_nfc_tag(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, hass_admin_user
) -> None:
    hass.states.async_set(
        "person.steven",
        "home",
        {"friendly_name": "Steven", "user_id": hass_admin_user.id},
    )
    manager = await start(
        hass,
        freezer,
        acknowledge=[{"type": "notify_action"}, {"type": "tag", "tag_id": "tonne"}],
    )

    async def scan(tag_id: str) -> None:
        hass.bus.async_fire(
            "tag_scanned",
            {"tag_id": tag_id, "device_id": "abc"},
            context=Context(user_id=hass_admin_user.id),
        )
        await hass.async_block_till_done()

    # Monday 15:00, before the reminder time: planned -> done.
    await tick(hass, freezer, at(MON, 15, 0))
    await scan("anderer_tag")
    assert manager.status("muell")["state"] == "planned"
    await scan("tonne")
    reminder = manager.reminders["muell"][REMINDER]
    assert reminder.state == "done"
    assert reminder.acknowledged_by == "Steven"
    assert reminder.acknowledged_via == "tag"


async def test_acknowledge_by_trigger(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    door = {"trigger": "state", "entity_id": DOOR, "to": "on"}
    manager = await start(
        hass,
        freezer,
        acknowledge=[{"type": "trigger", "trigger": door}],
        early={"mode": "off"},
    )
    (listener,) = manager.runners["muell"]._ack_triggers
    assert not listener.active

    # Before the reminder time the door does nothing.
    await switch(hass, DOOR, "on")
    await switch(hass, DOOR, "off")
    assert manager.status("muell")["state"] == "planned"

    await tick(hass, freezer, at(MON, 17, 0))
    assert listener.active
    await switch(hass, DOOR, "on")
    reminder = manager.reminders["muell"][REMINDER]
    assert reminder.state == "done"
    assert reminder.acknowledged_via == "trigger"
    assert not listener.active


async def test_acknowledge_by_trigger_early(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    door = {"trigger": "state", "entity_id": DOOR, "to": "on"}
    manager = await start(
        hass, freezer, acknowledge=[{"type": "trigger", "trigger": door}]
    )
    await hass.async_block_till_done()
    await switch(hass, DOOR, "on")
    assert manager.status("muell")["state"] == "done"


async def test_no_listener_left_after_unload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    door = {"trigger": "state", "entity_id": DOOR, "to": "on"}
    manager = await start(
        hass,
        freezer,
        signals=[push(lamp_on())],
        acknowledge=[
            {"type": "trigger", "trigger": door},
            {"type": "tag", "tag_id": "tonne"},
        ],
    )
    await tick(hass, freezer, at(MON, 17, 0))
    entry = hass.config_entries.async_entries("laeutwerk")[0]
    assert await hass.config_entries.async_unload(entry.entry_id)

    await toggle_lamp(hass)
    await switch(hass, DOOR, "on")
    hass.bus.async_fire("tag_scanned", {"tag_id": "tonne"})
    await tick(hass, freezer, at(MON, 17, 0) + timedelta(hours=1))
    assert not pushes
    assert manager.reminders["muell"][REMINDER].state == "reminded"
