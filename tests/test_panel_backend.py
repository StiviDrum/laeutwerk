"""Preview passes, event log and snooze until home."""

from __future__ import annotations

from datetime import date
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
import pytest

from custom_components.laeutwerk.const import DOMAIN, EVENTS_MAX
from custom_components.laeutwerk.diagnostics import async_get_config_entry_diagnostics

from .common import PHONE, WASTE, FakeCalendars, at, muell_rule, setup_integration, tick
from .ha_testing import MockConfigEntry, WebSocketGenerator, async_mock_service

MON = date(2026, 11, 16)
TUE = date(2026, 11, 17)
PERSON = "person.steven"


@pytest.fixture
def frozen(freezer: FrozenDateTimeFactory) -> FrozenDateTimeFactory:
    """Monday 09:00 before any websocket token is created."""
    freezer.move_to(at(MON, 9))
    return freezer


def push(**extra: Any) -> dict[str, Any]:
    return {"id": "push", "type": "notify", "targets": [PHONE], "message": "x", **extra}


def staged_rule(**changes: Any) -> dict[str, Any]:
    return muell_rule(
        **{
            "repeat": {"every": "90m", "max": 2},
            "escalation": [{"after": "2h"}, {"after": "21:30", "min_age": "2h"}],
            "signals": [
                push(id="first", send_on="first"),
                push(id="again", send_on="repeat"),
                push(id="stg", send_on="stage", stage=1),
                push(id="off", enabled=False),
            ],
            **changes,
        }
    )


def sent(calls: list[Any]) -> int:
    return len([c for c in calls if c.data["message"] != "clear_notification"])


async def ws_call(client: Any, mid: int, **msg: Any) -> dict[str, Any]:
    await client.send_json({"id": mid, **msg})
    reply = await client.receive_json()
    assert reply["success"], reply
    return reply["result"]


async def test_preview_passes(
    hass: HomeAssistant,
    frozen: FrozenDateTimeFactory,
    hass_ws_client: WebSocketGenerator,
) -> None:
    async_mock_service(hass, "notify", PHONE.split(".")[1])
    FakeCalendars(hass, WASTE).add_all_day(WASTE, "Papier", TUE)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(staged_rule())
    ws = await hass_ws_client(hass)

    result = await ws_call(ws, 1, type="laeutwerk/preview", rule_id="muell", passes=10)
    got = [
        (p["at"][11:16], p["kind"], p["nr"], p["stage"], p["signals"])
        for p in result["passes"]
    ]
    # Times are UTC (Berlin is UTC+1 in November).
    assert got == [
        ("16:00", "first", 1, None, ["first"]),
        ("17:30", "repeat", 2, None, ["again"]),
        ("18:00", "stage", 3, 1, ["again", "stg"]),
        ("19:00", "repeat", 4, None, ["again"]),
        ("20:30", "stage", 5, 2, ["again"]),
    ]
    assert result["passes"][0]["event_id"] == "muell__20261117"
    assert "sample" not in result["passes"][0]
    assert (
        len(
            (await ws_call(ws, 2, type="laeutwerk/preview", rule_id="muell", passes=2))[
                "passes"
            ]
        )
        == 2
    )

    # Draft: stage 2 is closer than min_age to the first reminder -> skipped.
    draft = staged_rule(escalation=[{"after": "21:30", "min_age": "5h"}])
    result = await ws_call(ws, 3, type="laeutwerk/preview", rule=draft, passes=10)
    assert [p["kind"] for p in result["passes"]] == ["first", "repeat", "repeat"]

    # Nothing after the reminder expires (event_day 12:00).
    draft = staged_rule(expire="-1d 17:30", escalation=[], signals=[push(id="first")])
    result = await ws_call(ws, 4, type="laeutwerk/preview", rule=draft, passes=10)
    assert [p["at"][11:16] for p in result["passes"]] == ["16:00"]


async def test_preview_days_and_trigger_sample(
    hass: HomeAssistant,
    frozen: FrozenDateTimeFactory,
    hass_ws_client: WebSocketGenerator,
) -> None:
    FakeCalendars(hass, WASTE).add_all_day(WASTE, "Papier", date(2026, 12, 20))
    await setup_integration(hass)
    ws = await hass_ws_client(hass)
    rule = muell_rule()
    assert (await ws_call(ws, 1, type="laeutwerk/preview", rule=rule))["events"] == []
    result = await ws_call(ws, 2, type="laeutwerk/preview", rule=rule, days=90)
    assert len(result["events"]) == 1
    assert result["passes"][0]["kind"] == "first"

    trigger = {
        "id": "klingel",
        "name": "Klingel",
        "start_triggers": [{"trigger": "state", "entity_id": "input_boolean.b"}],
        "repeat": {"every": "10m", "max": 1},
        "expire": "+1h",
        "signals": [push()],
    }
    result = await ws_call(ws, 3, type="laeutwerk/preview", rule=trigger)
    assert [(p["kind"], p["sample"]) for p in result["passes"]] == [
        ("first", True),
        ("repeat", True),
    ]
    assert result["passes"][0]["at"].startswith("2026-11-16T08:00")


async def test_event_log(
    hass: HomeAssistant,
    frozen: FrozenDateTimeFactory,
    hass_ws_client: WebSocketGenerator,
    hass_storage: dict[str, Any],
) -> None:
    FakeCalendars(hass, WASTE).add_all_day(WASTE, "Papier", TUE)
    async_mock_service(hass, "notify", PHONE.split(".")[1])
    entry, manager = await setup_integration(hass)
    await manager.async_create_rule(
        muell_rule(
            repeat={"every": "1h", "max": 1},
            signals=[
                push(
                    id="a",
                    when={
                        "opportunity": {
                            "trigger": "state",
                            "entity_id": "light.l",
                            "to": "on",
                        }
                    },
                    limit={"per_reminder": 1},
                ),
                push(id="b", enabled=False),
            ],
        )
    )
    await tick(hass, frozen, at(MON, 17, 0))
    for _ in range(2):
        hass.states.async_set("light.l", "off")
        await hass.async_block_till_done()
        hass.states.async_set("light.l", "on")
        await hass.async_block_till_done()
        await hass.async_block_till_done()
    await tick(hass, frozen, at(MON, 18, 0))
    await manager.async_snooze(30, "muell")
    await manager.async_acknowledge("muell", by="Steven", via="tag")
    kinds = [e["kind"] for e in reversed(manager.events)]
    assert kinds == [
        "reminded",
        "signal_skipped",  # b disabled
        "signal_sent",
        "signal_skipped",  # a limit
        "repeated",
        "signal_skipped",  # b disabled
        "snoozed",
        "acknowledged",
    ]
    ack = manager.events[0]
    assert (ack["person"], ack["via"], ack["rule_id"]) == ("Steven", "tag", "muell")
    assert {e.get("detail") for e in manager.events} >= {"disabled", "limit", "30m"}

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert len(diag["events"]) == 8

    # Survives a restart; ring buffer is bounded; rule deletion removes entries.
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert hass_storage["laeutwerk"]["minor_version"] == 5
    assert len(hass_storage["laeutwerk"]["data"]["events"]) == 8
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    manager = entry.runtime_data
    assert len(manager.events) == 8
    for n in range(EVENTS_MAX):
        manager.log_event({"ts": "x", "rule_id": "other", "kind": str(n)})
    assert len(manager.events) == EVENTS_MAX
    assert manager.events[0]["kind"] == str(EVENTS_MAX - 1)
    await manager.async_delete_rule("muell")
    assert all(e["rule_id"] != "muell" for e in manager.events)


async def test_events_websocket(
    hass: HomeAssistant,
    frozen: FrozenDateTimeFactory,
    hass_ws_client: WebSocketGenerator,
) -> None:
    _, manager = await setup_integration(hass)
    for ts, rule, kind in (
        ("2026-11-16T10:00:00+00:00", "a", "reminded"),
        ("2026-11-16T11:00:00+00:00", "b", "signal_sent"),
        ("2026-11-16T12:00:00+00:00", "a", "acknowledged"),
    ):
        manager.log_event({"ts": ts, "rule_id": rule, "reminder_id": "r", "kind": kind})
    ws = await hass_ws_client(hass)
    res = await ws_call(ws, 1, type="laeutwerk/events", rule_id="a")
    assert [e["kind"] for e in res["events"]] == ["acknowledged", "reminded"]
    res = await ws_call(ws, 2, type="laeutwerk/events", kinds=["signal_sent"])
    assert [e["rule_id"] for e in res["events"]] == ["b"]
    res = await ws_call(ws, 3, type="laeutwerk/events", since="2026-11-16T11:00:00Z")
    assert [e["kind"] for e in res["events"]] == ["acknowledged", "signal_sent"]
    res = await ws_call(ws, 4, type="laeutwerk/events", limit=1)
    assert [e["kind"] for e in res["events"]] == ["acknowledged"]


async def test_storage_migration_adds_events(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    hass_storage["laeutwerk"] = {
        "version": 1,
        "minor_version": 4,
        "key": "laeutwerk",
        "data": {"rules": [], "reminders": {}, "history": {}, "templates": []},
    }
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.events == []


# ------------------------------------------------------------ until home


async def _setup_snooze(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, person_state: str
) -> tuple[Any, Any, Any]:
    freezer.move_to(at(MON, 9))
    hass.states.async_set(PERSON, person_state, {"friendly_name": "Steven"})
    FakeCalendars(hass, WASTE).add_all_day(WASTE, "Papier", TUE)
    calls = async_mock_service(hass, "notify", PHONE.split(".")[1])
    entry, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule(signals=[push()]))
    await tick(hass, freezer, at(MON, 17, 0))
    assert sent(calls) == 1
    return entry, manager, calls


async def _set(hass: HomeAssistant, state: str) -> None:
    hass.states.async_set(PERSON, state, {"friendly_name": "Steven"})
    await hass.async_block_till_done()
    await hass.async_block_till_done()


async def test_snooze_until_home_away(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    _, manager, calls = await _setup_snooze(hass, freezer, "not_home")
    result = await hass.services.async_call(
        DOMAIN, "snooze", {"until_home": PERSON}, blocking=True, return_response=True
    )
    assert result == {"snoozed": ["muell__20261117"]}
    reminder = manager.reminders["muell"]["muell__20261117"]
    assert (reminder.state, reminder.snoozed_until_home) == ("planned", PERSON)
    assert reminder.snoozed_home_phase == "arrive"
    # Deadline: one minute before the expiry (Tue 12:00 local = 11:00 UTC).
    assert reminder.snoozed_until.isoformat().startswith("2026-11-17T10:59")
    status = manager.status("muell")["reminders"][0]
    assert status["snoozed_until_home_name"] == "Steven"
    assert manager.events[0]["detail"] == "until_home"

    await _set(hass, "home")
    assert reminder.state == "reminded"
    assert reminder.snoozed_until_home is None and reminder.snoozed_until is None
    assert sent(calls) == 2
    assert not manager.runners["muell"]._home_unsubs


async def test_snooze_until_home_present_and_restart(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry, manager, calls = await _setup_snooze(hass, freezer, "home")
    await manager.async_snooze_until_home(PERSON, "muell")
    reminder = manager.reminders["muell"]["muell__20261117"]
    assert reminder.snoozed_home_phase == "leave"
    await _set(hass, "home")  # no change of phase
    assert reminder.state == "planned"

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    manager = entry.runtime_data
    reminder = manager.reminders["muell"]["muell__20261117"]
    assert reminder.snoozed_home_phase == "leave"
    assert manager.runners["muell"]._home_unsubs

    await _set(hass, "not_home")
    assert reminder.snoozed_home_phase == "arrive"
    assert reminder.state == "planned"
    await _set(hass, "home")
    assert reminder.state == "reminded"
    assert sent(calls) == 2


async def test_snooze_until_home_deadline_and_ack(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    _, manager, calls = await _setup_snooze(hass, freezer, "not_home")
    await manager.async_snooze_until_home(PERSON, "muell")
    runner = manager.runners["muell"]
    await tick(hass, freezer, at(TUE, 11, 58))
    assert sent(calls) == 1
    await tick(hass, freezer, at(TUE, 11, 59))  # still away: due again anyway
    assert sent(calls) == 2
    assert not runner._home_unsubs
    assert manager.reminders["muell"]["muell__20261117"].snoozed_until_home is None


async def test_snooze_until_home_ack_unsubscribes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    _, manager, _calls = await _setup_snooze(hass, freezer, "not_home")
    await manager.async_snooze_until_home(PERSON, "muell")
    runner = manager.runners["muell"]
    assert runner._home_unsubs
    await manager.async_acknowledge("muell")
    assert not runner._home_unsubs
