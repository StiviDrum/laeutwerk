"""Reminder lifecycle with a running Home Assistant (frozen time)."""

from __future__ import annotations

from datetime import date, timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import Context, Event, HomeAssistant, ServiceCall, callback
import pytest

from custom_components.laeutwerk.const import (
    EVENT_ACKNOWLEDGED,
    EVENT_MISSED,
    EVENT_REMINDED,
    EVENT_SIGNAL_SENT,
)
from custom_components.laeutwerk.manager import LaeutwerkManager

from .common import (
    KULT,
    PHONE,
    WASTE,
    FakeCalendars,
    at,
    kult61_rule,
    muell_rule,
    setup_integration,
    tick,
)
from .ha_testing import async_mock_service

MON = date(2026, 11, 16)
TUE = date(2026, 11, 17)
REMINDER = "muell__20261117"


@pytest.fixture
def calendars(hass: HomeAssistant) -> FakeCalendars:
    return FakeCalendars(hass, WASTE, KULT)


@pytest.fixture
def pushes(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "notify", PHONE.split(".")[1])


@pytest.fixture
def events(hass: HomeAssistant) -> list[Event]:
    captured: list[Event] = []

    @callback
    def capture(event: Event) -> None:
        captured.append(event)

    for event_type in (
        EVENT_REMINDED,
        EVENT_SIGNAL_SENT,
        EVENT_ACKNOWLEDGED,
        EVENT_MISSED,
    ):
        hass.bus.async_listen(event_type, capture)
    return captured


def types(events: list[Event]) -> list[str]:
    return [event.event_type.removeprefix("laeutwerk_") for event in events]


def state(manager: LaeutwerkManager, rule_id: str = "muell") -> str:
    return manager.status(rule_id)["state"]


async def test_lifecycle_push_and_acknowledge(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calendars: FakeCalendars,
    pushes: list[ServiceCall],
    events: list[Event],
) -> None:
    """Planned -> reminded at 17:00 the day before (one push) -> done."""
    freezer.move_to(at(MON, 9))
    calendars.add_all_day(WASTE, "Papier", TUE)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await hass.async_block_till_done()

    assert state(manager) == "planned"
    assert list(manager.reminders["muell"]) == [REMINDER]

    await tick(hass, freezer, at(MON, 16, 59))
    assert state(manager) == "planned"
    assert not pushes

    await tick(hass, freezer, at(MON, 17, 0))
    assert state(manager) == "reminded"
    assert len(pushes) == 1
    assert pushes[0].data == {
        "title": "Morgen: Papiertonne",
        "message": "Bitte heute Abend die Papiertonne rausstellen.",
        "data": {
            "tag": f"laeutwerk_{REMINDER}",
            "actions": [
                {"action": f"LAEUTWERK_ACK__{REMINDER}", "title": "Steht draußen"}
            ],
        },
    }
    assert types(events) == ["reminded", "signal_sent"]
    assert events[0].data["rule_id"] == "muell"
    assert events[0].data["reminder_time"] == "-1d 17:00"
    assert events[0].data["variables"]["tonne"] == "Papiertonne"
    assert events[1].data["signal_id"] == "push"

    # Later refreshes and timers never send again.
    await tick(hass, freezer, at(MON, 19, 0))
    assert len(pushes) == 1

    done = await manager.async_acknowledge("muell", by="Steven", via="service")
    await hass.async_block_till_done()
    assert [r.id for r in done] == [REMINDER]
    assert state(manager) == "done"
    reminder = manager.reminders["muell"][REMINDER]
    assert reminder.acknowledged_by == "Steven"
    assert types(events)[-1] == "acknowledged"
    assert events[-1].data["acknowledged_by"] == "Steven"
    # The notification is removed from the phone.
    assert pushes[-1].data == {
        "message": "clear_notification",
        "data": {"tag": f"laeutwerk_{REMINDER}"},
    }

    # Done stays done: no "missed" at the expiry, state shown until the day ends.
    await tick(hass, freezer, at(TUE, 12, 1))
    assert state(manager) == "done"
    assert "missed" not in types(events)
    await tick(hass, freezer, at(TUE + timedelta(days=1), 0, 20))
    assert state(manager) == "inactive"


async def test_bundle_is_one_reminder_with_plural_text(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calendars: FakeCalendars,
    pushes: list[ServiceCall],
) -> None:
    freezer.move_to(at(MON, 9))
    calendars.add_all_day(WASTE, "Papier", TUE)
    calendars.add_all_day(WASTE, "Bio", TUE)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await tick(hass, freezer, at(MON, 17, 0))

    assert len(pushes) == 1
    assert pushes[0].data["title"] == "Morgen: Biotonne und Papiertonne"
    assert pushes[0].data["message"] == (
        "Bitte heute Abend rausstellen: Biotonne und Papiertonne."
    )
    # One acknowledgement finishes the whole bundle.
    await manager.async_acknowledge("muell")
    assert state(manager) == "done"
    assert not manager.runners["muell"].open_reminders


async def test_expiry_marks_missed(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calendars: FakeCalendars,
    pushes: list[ServiceCall],
    events: list[Event],
) -> None:
    freezer.move_to(at(MON, 9))
    calendars.add_all_day(WASTE, "Rest", TUE)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await tick(hass, freezer, at(MON, 17, 0))
    await tick(hass, freezer, at(TUE, 11, 59))
    assert state(manager) == "reminded"

    await tick(hass, freezer, at(TUE, 12, 0))
    assert state(manager) == "missed"
    assert types(events) == ["reminded", "signal_sent", "missed"]
    assert pushes[-1].data["message"] == "clear_notification"
    # Too late now.
    assert await manager.async_acknowledge("muell") == []
    assert state(manager) == "missed"


async def test_early_acknowledge_before_reminder_time(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calendars: FakeCalendars,
    pushes: list[ServiceCall],
) -> None:
    """Planned -> done, e.g. NFC tag at the bin in the afternoon."""
    freezer.move_to(at(MON - timedelta(days=3), 9))
    calendars.add_all_day(WASTE, "Papier", TUE)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await hass.async_block_till_done()

    # More than 24 h before the reminder time: a plain "done" does nothing.
    assert await manager.async_acknowledge("muell") == []
    assert state(manager) == "planned"

    await tick(hass, freezer, at(MON, 15, 0))
    assert len(await manager.async_acknowledge("muell")) == 1
    assert state(manager) == "done"

    await tick(hass, freezer, at(MON, 17, 0))
    await tick(hass, freezer, at(TUE, 12, 0))
    assert not pushes
    assert state(manager) == "done"


async def test_restart_sends_nothing_twice(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calendars: FakeCalendars,
    pushes: list[ServiceCall],
) -> None:
    freezer.move_to(at(MON, 9))
    calendars.add_all_day(WASTE, "Papier", TUE)
    entry, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await tick(hass, freezer, at(MON, 17, 0))
    assert len(pushes) == 1

    assert await hass.config_entries.async_unload(entry.entry_id)
    freezer.move_to(at(MON, 18, 30))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    manager = entry.runtime_data

    assert state(manager) == "reminded"
    assert manager.reminders["muell"][REMINDER].fired == ["-1d 17:00"]
    assert len(pushes) == 1
    await tick(hass, freezer, at(MON, 23, 0))
    assert len(pushes) == 1

    # The open reminder survived and can still be acknowledged.
    assert len(await manager.async_acknowledge("muell")) == 1


async def test_catches_up_after_downtime(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calendars: FakeCalendars,
    pushes: list[ServiceCall],
) -> None:
    """Home Assistant was off at the reminder time: remind once afterwards."""
    freezer.move_to(at(MON, 9))
    calendars.add_all_day(WASTE, "Papier", TUE)
    entry, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)

    freezer.move_to(at(MON, 19, 0))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert state(entry.runtime_data) == "reminded"
    assert len(pushes) == 1
    assert pushes[0].data["title"] == "Morgen: Papiertonne"


async def test_event_already_over_creates_no_reminder(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calendars: FakeCalendars,
    pushes: list[ServiceCall],
    events: list[Event],
) -> None:
    """A new rule does not remind of (or miss) what has expired already."""
    freezer.move_to(at(TUE, 14))
    calendars.add_all_day(WASTE, "Papier", TUE)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await hass.async_block_till_done()
    assert manager.reminders["muell"] == {}
    assert state(manager) == "inactive"
    assert not pushes
    assert not events


async def test_several_reminder_times(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calendars: FakeCalendars,
    pushes: list[ServiceCall],
    events: list[Event],
) -> None:
    """Kult61: the evening before and 2 h before the shift."""
    friday = date(2026, 11, 20)
    freezer.move_to(at(MON, 9))
    calendars.add_timed(KULT, "Dienst: Theke", at(friday, 19))
    calendars.add_timed(KULT, "Plenum", at(friday, 17))
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(kult61_rule())
    await hass.async_block_till_done()
    assert list(manager.reminders["kult61"]) == ["kult61__20261120"]

    await tick(hass, freezer, at(friday - timedelta(days=1), 20, 0))
    assert len(pushes) == 1
    assert pushes[0].data["message"] == (
        "Denk an deinen Dienst morgen: Theke, ab 19:00."
    )
    assert "title" not in pushes[0].data

    await tick(hass, freezer, at(friday, 16, 59))
    assert len(pushes) == 1
    await tick(hass, freezer, at(friday, 17, 0))
    assert len(pushes) == 2
    assert pushes[1].data["message"] == "Denk an deinen Dienst heute: Theke, ab 19:00."
    assert [e.data["reminder_time"] for e in events if "reminded" in e.event_type] == [
        "-1d 20:00",
        "-2h",
    ]

    # Next week: acknowledged after the first reminder, so the second
    # reminder time (2 h before) sends nothing.
    calendars.add_timed(KULT, "Dienst: Kasse", at(friday + timedelta(days=7), 18))
    await tick(hass, freezer, at(friday, 23, 30))
    assert state(manager, "kult61") == "missed"
    await tick(hass, freezer, at(friday + timedelta(days=6), 20, 0))
    assert len(pushes) == 4  # clear + reminder for the next shift
    await manager.async_acknowledge("kult61")
    await tick(hass, freezer, at(friday + timedelta(days=7), 16, 0))
    assert [call.data["message"] for call in pushes[3:]] == [
        "Denk an deinen Dienst morgen: Kasse, ab 18:00.",
        "clear_notification",
    ]


async def test_notification_action_acknowledges_with_person(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calendars: FakeCalendars,
    pushes: list[ServiceCall],
    hass_admin_user,
) -> None:
    freezer.move_to(at(MON, 9))
    calendars.add_all_day(WASTE, "Papier", TUE)
    hass.states.async_set(
        "person.steven",
        "home",
        {"friendly_name": "Steven", "user_id": hass_admin_user.id},
    )
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await tick(hass, freezer, at(MON, 17, 0))

    hass.bus.async_fire("mobile_app_notification_action", {"action": "SOMETHING_ELSE"})
    await hass.async_block_till_done()
    assert state(manager) == "reminded"

    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": pushes[0].data["data"]["actions"][0]["action"]},
        context=Context(user_id=hass_admin_user.id),
    )
    await hass.async_block_till_done()
    reminder = manager.reminders["muell"][REMINDER]
    assert reminder.state == "done"
    assert reminder.acknowledged_by == "Steven"
    assert reminder.acknowledged_via == "notify_action"


async def test_calendar_changes_are_followed(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calendars: FakeCalendars,
    pushes: list[ServiceCall],
) -> None:
    """New events join the bundle, removed events drop the reminder."""
    freezer.move_to(at(MON, 9))
    calendars.add_all_day(WASTE, "Papier", TUE)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await tick(hass, freezer, at(MON, 17, 0))
    assert len(pushes) == 1

    # A second bin is added after the reminder: same reminder, no new push.
    calendars.add_all_day(WASTE, "Bio", TUE)
    calendars.touch(WASTE)
    await tick(hass, freezer, at(MON, 17, 1))
    reminder = manager.reminders["muell"][REMINDER]
    assert [e.summary for e in reminder.events] == ["Bio", "Papier"]
    assert len(pushes) == 1

    # A broken calendar keeps what is known.
    calendars.failing.add(WASTE)
    await tick(hass, freezer, at(MON, 17, 20))
    assert state(manager) == "reminded"
    assert manager.status("muell")["errors"] == {WASTE: f"{WASTE} is broken"}
    calendars.failing.clear()

    # Both events are removed: the reminder disappears, the push is cleared.
    calendars.remove(WASTE, "Papier")
    calendars.remove(WASTE, "Bio")
    await tick(hass, freezer, at(MON, 17, 40))
    assert manager.reminders["muell"] == {}
    assert manager.status("muell")["errors"] == {}
    assert pushes[-1].data["message"] == "clear_notification"
    assert state(manager) == "inactive"


async def test_missing_calendar_is_reported(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calendars: FakeCalendars
) -> None:
    freezer.move_to(at(MON, 9))
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule(sources=["calendar.gibt_es_nicht"]))
    await hass.async_block_till_done()
    assert manager.status("muell")["errors"] == {
        "calendar.gibt_es_nicht": "calendar not found"
    }


async def test_disable_drops_open_reminders_and_unload_cleans_up(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calendars: FakeCalendars,
    pushes: list[ServiceCall],
) -> None:
    freezer.move_to(at(MON, 9))
    calendars.add_all_day(WASTE, "Papier", TUE)
    entry, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await tick(hass, freezer, at(MON, 17, 0))

    await manager.async_set_enabled("muell", False)
    await hass.async_block_till_done()
    assert state(manager) == "inactive"
    assert manager.reminders["muell"] == {}
    assert pushes[-1].data["message"] == "clear_notification"

    # Nothing happens while off; switching on reminds again (still due).
    calls = calendars.calls
    calendars.touch(WASTE)
    await tick(hass, freezer, at(MON, 17, 30))
    assert calendars.calls == calls
    await manager.async_set_enabled("muell", True)
    await hass.async_block_till_done()
    assert state(manager) == "reminded"

    # After unloading no listener or timer is left.
    assert await hass.config_entries.async_unload(entry.entry_id)
    calls, sent = calendars.calls, len(pushes)
    calendars.touch(WASTE)
    await tick(hass, freezer, at(TUE, 12, 30))
    assert calendars.calls == calls
    assert len(pushes) == sent


async def test_spring_forward(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calendars: FakeCalendars,
    pushes: list[ServiceCall],
) -> None:
    """29 March 2026 (02:00 -> 03:00): wall-clock reminders stay on the clock."""
    saturday, sunday, monday = date(2026, 3, 28), date(2026, 3, 29), date(2026, 3, 30)
    freezer.move_to(at(saturday, 9))
    calendars.add_all_day(WASTE, "Papier", monday)
    calendars.add_all_day(WASTE, "Bio", sunday)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(
        muell_rule(reminders=[{"at": "-1d 17:00"}, {"at": "02:30"}], expire="event_end")
    )
    await hass.async_block_till_done()

    # Saturday 17:00 CET: reminder for Sunday.
    await tick(hass, freezer, at(saturday, 16, 59))
    assert not pushes
    await tick(hass, freezer, at(saturday, 17, 0))
    assert [c.data["title"] for c in pushes] == ["Morgen: Biotonne"]

    # 02:30 does not exist on Sunday: it fires at 03:00 CEST (01:00 UTC).
    await tick(hass, freezer, at(sunday, 1, 59))
    assert len(pushes) == 1
    await tick(hass, freezer, at(sunday, 3, 0))
    assert [c.data["title"] for c in pushes[1:]] == ["Heute: Biotonne"]

    # Sunday 17:00 CEST (15:00 UTC, not 16:00 UTC): reminder for Monday.
    await tick(hass, freezer, at(sunday, 16, 59))
    assert len(pushes) == 2
    await tick(hass, freezer, at(sunday, 17, 0))
    assert [c.data["title"] for c in pushes[2:]] == ["Morgen: Papiertonne"]
    # Sunday's reminder expires at midnight, Monday's stays open.
    await tick(hass, freezer, at(monday, 0, 1))
    assert [r.state for r in manager.reminders["muell"].values()] == [
        "missed",
        "reminded",
    ]


async def test_fall_back(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calendars: FakeCalendars,
    pushes: list[ServiceCall],
) -> None:
    """25 October 2026 (03:00 -> 02:00): the repeated hour fires only once."""
    saturday, sunday, monday = (
        date(2026, 10, 24),
        date(2026, 10, 25),
        date(2026, 10, 26),
    )
    freezer.move_to(at(saturday, 9))
    calendars.add_all_day(WASTE, "Bio", sunday)
    calendars.add_all_day(WASTE, "Papier", monday)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(
        muell_rule(reminders=[{"at": "02:30"}, {"at": "-1d 17:00"}], expire="event_end")
    )
    await hass.async_block_till_done()

    await tick(hass, freezer, at(saturday, 17, 0))
    assert [c.data["title"] for c in pushes] == ["Morgen: Biotonne"]

    first_pass = at(sunday, 2, 30).replace(fold=0)
    second_pass = at(sunday, 2, 30).replace(fold=1)
    assert second_pass.utcoffset() != first_pass.utcoffset()
    await tick(hass, freezer, first_pass - timedelta(minutes=1))
    assert len(pushes) == 1
    await tick(hass, freezer, first_pass)
    assert [c.data["title"] for c in pushes[1:]] == ["Heute: Biotonne"]
    await tick(hass, freezer, second_pass)
    await tick(hass, freezer, at(sunday, 3, 30))
    assert len(pushes) == 2

    # Sunday 17:00 CET (16:00 UTC): reminder for Monday, exactly once.
    await tick(hass, freezer, at(sunday, 16, 59))
    assert len(pushes) == 2
    await tick(hass, freezer, at(sunday, 17, 0))
    await tick(hass, freezer, at(sunday, 18, 0))
    assert [c.data["title"] for c in pushes[2:]] == ["Morgen: Papiertonne"]
