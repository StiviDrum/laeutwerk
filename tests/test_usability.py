"""0.7 usability backend: snooze until, reopen, suggestions, draft test, reorder."""

from __future__ import annotations

from datetime import date
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
import pytest

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
def pushes(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "notify", PHONE.split(".")[1])


async def start(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, **changes: Any
) -> tuple[LaeutwerkManager, FakeCalendars]:
    freezer.move_to(at(MON, 9))
    calendars = FakeCalendars(hass, WASTE, KULT)
    calendars.add_all_day(WASTE, "Papier", TUE)
    calendars.add_all_day(WASTE, "Biomüll", TUE)
    calendars.add_all_day(WASTE, "Biomüll", date(2026, 12, 1))
    calendars.add_all_day(WASTE, "Weihnachtsbaum", date(2027, 1, 8))
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule(**changes))
    await hass.async_block_till_done()
    return manager, calendars


async def call(hass: HomeAssistant, service: str, **data: Any) -> Any:
    result = await hass.services.async_call(
        "laeutwerk", service, data, blocking=True, return_response=True
    )
    await hass.async_block_till_done()
    return result


# ------------------------------------------------------------ snooze until


async def test_snooze_until_time_of_day(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    manager, _ = await start(hass, freezer, expire="event_end")
    await tick(hass, freezer, at(MON, 17, 0))
    # "morgen früh": 07:00 is already over today -> tomorrow 07:00.
    assert await call(hass, "snooze", until="07:00") == {"snoozed": [REMINDER]}
    assert manager.reminders["muell"][REMINDER].snoozed_until == at(TUE, 7, 0)
    await tick(hass, freezer, at(TUE, 7, 0))
    assert manager.status("muell")["state"] == "reminded"
    # Later the same day: 20:00 today.
    await call(hass, "snooze", until="20:00")
    assert manager.reminders["muell"][REMINDER].snoozed_until == at(TUE, 20, 0)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("laeutwerk", "snooze", {}, blocking=True)


# ------------------------------------------------------------------- reopen


async def test_reopen_after_mis_tap(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    manager, _ = await start(hass, freezer)
    await tick(hass, freezer, at(MON, 17, 0))
    await manager.async_acknowledge("muell", by="Steven", via="button")
    assert manager.history["muell"][0]["reminder_id"] == REMINDER
    sent = len(pushes)

    assert await call(hass, "reopen", reminder_id=REMINDER) == {"reopened": REMINDER}
    reminder = manager.reminders["muell"][REMINDER]
    assert (reminder.state, reminder.acknowledged_by, reminder.finished_at) == (
        "reminded",
        None,
        None,
    )
    assert manager.history.get("muell") == []
    assert hass.states.get("binary_sensor.laeutwerk_muell_offen").state == "on"
    assert len(pushes) == sent  # nothing is sent again

    # Still expires as usual, and cannot be reopened once over.
    await manager.async_acknowledge("muell")
    await tick(hass, freezer, at(TUE, 12, 0))
    with pytest.raises(ServiceValidationError, match="cannot be reopened"):
        await call(hass, "reopen", reminder_id=REMINDER)
    with pytest.raises(ServiceValidationError):
        await call(hass, "reopen", reminder_id="gibt_es_nicht")


async def test_reopen_early_acknowledged_is_planned_again(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    manager, _ = await start(hass, freezer)
    await tick(hass, freezer, at(MON, 15, 0))
    await manager.async_acknowledge("muell")
    await manager.async_reopen(REMINDER)
    assert manager.reminders["muell"][REMINDER].state == "planned"
    await tick(hass, freezer, at(MON, 17, 0))
    assert manager.status("muell")["state"] == "reminded"


async def test_reopen_interval_due_again(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(at(MON, 8))
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(
        {
            "id": "f",
            "name": "Filter",
            "interval": {"every": 30},
            "reminders": [{"at": "09:00"}],
        }
    )
    await tick(hass, freezer, at(MON, 9, 0))
    await manager.async_acknowledge("f")
    await hass.async_block_till_done()
    assert manager.status("f")["next_event"]["day"] == "2026-12-16"
    await manager.async_reopen("f__20261116")
    await hass.async_block_till_done()
    assert manager.status("f")["next_event"]["day"] == "2026-11-16"


# -------------------------------------------------------- title suggestions


async def test_title_suggestions(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(at(MON, 9))
    calendars = FakeCalendars(hass, WASTE)
    for day, title in (
        (TUE, "Papier"),
        (TUE, "Biomüll"),
        (date(2026, 12, 1), "Biomüll"),
        (date(2026, 12, 20), "Gelbe Tonne"),
        (date(2027, 2, 1), "Weihnachtsbaum"),  # beyond 60 days
    ):
        calendars.add_all_day(WASTE, title, day)
    _, manager = await setup_integration(hass)
    rule = {
        "sources": [WASTE],
        "filter": {"keywords": {"rows": [{"match": "Papier"}]}},
    }
    titles = await manager.async_title_suggestions(rule)
    # In the order of their first event.
    assert titles == [
        {"title": "Papier", "count": 1, "matched": True},
        {"title": "Biomüll", "count": 2, "matched": False},
        {"title": "Gelbe Tonne", "count": 1, "matched": False},
    ]
    # Without keywords nothing counts as matched (every event would).
    assert not any(
        t["matched"]
        for t in await manager.async_title_suggestions({"sources": [WASTE]})
    )


async def test_preview_with_titles(hass: HomeAssistant, hass_ws_client) -> None:
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", date.today())
    await setup_integration(hass)
    ws = await hass_ws_client(hass)
    await ws.send_json(
        {
            "id": 1,
            "type": "laeutwerk/preview",
            "rule": {"sources": [WASTE]},
            "titles": True,
        }
    )
    result = (await ws.receive_json())["result"]
    assert result["titles"] == [{"title": "Papier", "count": 1, "matched": False}]
    await ws.send_json(
        {"id": 2, "type": "laeutwerk/preview", "rule": {"sources": [WASTE]}}
    )
    assert "titles" not in (await ws.receive_json())["result"]


# --------------------------------------------- test signal of unsaved rule


async def test_test_signal_for_unsaved_rule(
    hass: HomeAssistant, pushes: list[ServiceCall], hass_ws_client
) -> None:
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", date.today())
    await setup_integration(hass)
    ws = await hass_ws_client(hass)
    draft = muell_rule(id=None, name="", reminders=[], signals=[])
    signal = {"id": "x", "type": "notify", "targets": [PHONE], "message": "{tonne}"}
    await ws.send_json(
        {"id": 1, "type": "laeutwerk/test_signal", "rule": draft, "signal": signal}
    )
    assert (await ws.receive_json())["result"] == {"sent": True}
    assert pushes[-1].data["message"] == "Papiertonne"
    # Unknown target: a clear error.
    signal["targets"] = ["notify.nobody"]
    await ws.send_json(
        {"id": 2, "type": "laeutwerk/test_signal", "rule": draft, "signal": signal}
    )
    assert (await ws.receive_json())["error"]["code"] == "home_assistant_error"


# ------------------------------------------------------------------ reorder


async def test_reorder(hass: HomeAssistant, hass_ws_client) -> None:
    FakeCalendars(hass, WASTE, KULT)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await manager.async_create_rule(kult61_rule())
    await manager.async_create_rule(muell_rule(id="drei", name="Drei"))
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "laeutwerk/rules/subscribe"})
    await ws.receive_json()
    await ws.receive_json()  # init

    await ws.send_json(
        {"id": 2, "type": "laeutwerk/rules/reorder", "rule_ids": ["drei", "muell"]}
    )
    msgs = [await ws.receive_json(), await ws.receive_json()]
    event = next(m["event"] for m in msgs if m["type"] == "event")
    result = next(m["result"] for m in msgs if m["type"] == "result")
    assert event == {"event": "reordered", "rule_ids": ["drei", "muell", "kult61"]}
    assert result == {"rule_ids": ["drei", "muell", "kult61"]}
    assert list(manager.rules) == ["drei", "muell", "kult61"]
    rules = await call(hass, "get_rules")
    assert [r["id"] for r in rules["rules"]] == ["drei", "muell", "kult61"]
    await ws.send_json(
        {"id": 3, "type": "laeutwerk/rules/reorder", "rule_ids": ["nope"]}
    )
    assert (await ws.receive_json())["error"]["code"] == "not_found"


async def test_planned_reminder_can_be_done_ahead_by_id(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The compact card asks first, then acknowledges by id – also days ahead."""
    freezer.move_to(at(MON, 9))
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", date(2026, 11, 24))  # a week ahead
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await hass.async_block_till_done()
    # The early setting (default 24 h) applies, also with an id (0.9.2) …
    result = await call(
        hass, "acknowledge", rule="muell", reminder_id="muell__20261124"
    )
    assert result["acknowledged"] == []
    assert result["too_early"]
    # … "always" allows it right away.
    await manager.async_update_rule(
        "muell", {**manager.rules["muell"].to_dict(), "early": {"mode": "always"}}
    )
    result = await call(
        hass, "acknowledge", rule="muell", reminder_id="muell__20261124"
    )
    assert result == {"acknowledged": ["muell__20261124"], "too_early": None}
    assert manager.reminders["muell"]["muell__20261124"].state == "done"
