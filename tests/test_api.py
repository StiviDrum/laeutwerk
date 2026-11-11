"""Websocket API used by the card."""

from __future__ import annotations

from datetime import date
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
import pytest

from custom_components.laeutwerk.manager import LaeutwerkManager

from .common import (
    KULT,
    WASTE,
    FakeCalendars,
    at,
    kult61_rule,
    muell_rule,
    setup_integration,
    tick,
)
from .ha_testing import WebSocketGenerator, async_mock_service

MON = date(2026, 11, 16)
TUE = date(2026, 11, 17)


@pytest.fixture
async def manager(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> LaeutwerkManager:
    freezer.move_to(at(MON, 9))
    calendars = FakeCalendars(hass, WASTE, KULT)
    calendars.add_all_day(WASTE, "Papier", TUE)
    calendars.add_all_day(WASTE, "Bio", TUE)
    calendars.add_all_day(WASTE, "Rest", date(2026, 11, 24))
    calendars.add_all_day(WASTE, "Sperrmüll", date(2026, 11, 25))
    calendars.add_timed(KULT, "Dienst: Theke", at(date(2026, 11, 20), 19))
    async_mock_service(hass, "notify", "mobile_app_steven")
    _, manager = await setup_integration(hass)
    return manager


class Client:
    def __init__(self, ws: Any) -> None:
        self.ws = ws
        self._id = 0

    async def send(self, type_: str, **data: Any) -> dict[str, Any]:
        self._id += 1
        await self.ws.send_json({"id": self._id, "type": f"laeutwerk/{type_}", **data})
        while True:
            msg = await self.ws.receive_json()
            if msg["type"] == "result" and msg["id"] == self._id:
                return msg

    async def ok(self, type_: str, **data: Any) -> Any:
        msg = await self.send(type_, **data)
        assert msg["success"], msg
        return msg["result"]

    async def error(self, type_: str, **data: Any) -> dict[str, Any]:
        msg = await self.send(type_, **data)
        assert not msg["success"]
        return msg["error"]


async def test_crud(
    hass: HomeAssistant, manager: LaeutwerkManager, hass_ws_client: WebSocketGenerator
) -> None:
    client = Client(await hass_ws_client(hass))
    assert await client.ok("rules/list") == {"rules": []}

    created = await client.ok("rules/create", rule=muell_rule())
    assert created["id"] == "muell"
    status = created["status"]
    assert status["state"] == "planned"
    reminder = status["reminders"][0]
    assert reminder["titles"] == ["Bio", "Papier"]
    assert reminder["colors"] == ["#008000", "#0000ff"]
    assert reminder["next_reminder_at"] == "2026-11-16T16:00:00+00:00"
    assert status["next_event"]["all_day"] is True

    got = await client.ok("rules/get", rule_id="muell")
    assert got["name"] == "Müll rausstellen"

    # The payload of get can be sent back (status is ignored).
    got["name"] = "Müll"
    updated = await client.ok("rules/update", rule_id="muell", rule=got)
    assert updated["name"] == "Müll"
    assert manager.rules["muell"].name == "Müll"

    copy = await client.ok("rules/duplicate", rule_id="muell")
    assert copy["id"] == "muell_kopie"
    assert copy["enabled"] is False
    assert len((await client.ok("rules/list"))["rules"]) == 2

    await client.ok("rules/delete", rule_id="muell_kopie")
    assert list(manager.rules) == ["muell"]

    assert (await client.error("rules/get", rule_id="nope"))["code"] == "not_found"
    assert (await client.error("rules/delete", rule_id="nope"))["code"] == "not_found"
    error = await client.error("rules/create", rule=muell_rule(id="x", reminders=[]))
    assert error["code"] == "invalid_format"
    assert "reminders" in error["message"]
    error = await client.error("rules/create", rule=muell_rule())
    assert "already exists" in error["message"]


async def test_writing_requires_admin(
    hass: HomeAssistant,
    manager: LaeutwerkManager,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_access_token: str,
) -> None:
    await manager.async_create_rule(muell_rule())
    client = Client(await hass_ws_client(hass, hass_read_only_access_token))
    assert len((await client.ok("rules/list"))["rules"]) == 1
    await client.ok("preview", rule_id="muell")
    for type_, data in (
        ("rules/create", {"rule": kult61_rule()}),
        ("rules/update", {"rule_id": "muell", "rule": muell_rule()}),
        ("rules/duplicate", {"rule_id": "muell"}),
        ("rules/delete", {"rule_id": "muell"}),
    ):
        assert (await client.error(type_, **data))["code"] == "unauthorized"
    assert list(manager.rules) == ["muell"]


async def test_subscribe(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    manager: LaeutwerkManager,
    hass_ws_client: WebSocketGenerator,
) -> None:
    await manager.async_create_rule(muell_rule())
    listeners_before = len(manager._listeners)
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "laeutwerk/rules/subscribe"})
    assert (await ws.receive_json())["success"]
    init = (await ws.receive_json())["event"]
    assert init["event"] == "init"
    assert [rule["id"] for rule in init["rules"]] == ["muell"]

    async def events_until(predicate) -> dict[str, Any]:
        while True:
            event = (await ws.receive_json())["event"]
            if predicate(event):
                return event

    # Status changes arrive live.
    await tick(hass, freezer, at(MON, 17, 0))
    event = await events_until(
        lambda e: e["event"] == "updated" and e["rule"]["status"]["state"] == "reminded"
    )
    assert event["rule_id"] == "muell"

    await manager.async_create_rule(kult61_rule())
    event = await events_until(lambda e: e["event"] == "added")
    assert event["rule"]["id"] == "kult61"

    await manager.async_delete_rule("kult61")
    event = await events_until(lambda e: e["event"] == "removed")
    assert event == {"event": "removed", "rule_id": "kult61", "rule": None}

    # After unsubscribing nothing is forwarded any more.
    await ws.send_json({"id": 2, "type": "unsubscribe_events", "subscription": 1})
    assert (await ws.receive_json())["success"]
    assert len(manager._listeners) == listeners_before


async def test_preview_saved_and_unsaved(
    hass: HomeAssistant, manager: LaeutwerkManager, hass_ws_client: WebSocketGenerator
) -> None:
    client = Client(await hass_ws_client(hass))
    await manager.async_create_rule(muell_rule())

    saved = await client.ok("preview", rule_id="muell")
    assert [e["titles"] for e in saved["events"]] == [["Bio", "Papier"], ["Rest"]]
    first = saved["events"][0]
    assert first["variables"]["tonnen"] == "Biotonne und Papiertonne"
    assert first["reminder_times"] == ["2026-11-16T16:00:00+00:00"]
    assert first["expires_at"] == "2026-11-17T11:00:00+00:00"
    assert first["colors"] == ["#008000", "#0000ff"]
    assert saved["total_events"] == 4
    assert saved["errors"] == {}
    assert "tonnen" in saved["variables"]
    assert "wann" in saved["variables"]

    # An unsaved rule: only what the editor has so far.
    unsaved = await client.ok(
        "preview",
        rule={
            "sources": [WASTE, KULT],
            "filter": {"keywords": {"rows": [{"match": "müll"}, {"match": "Dienst"}]}},
            "bundle": False,
        },
        limit=1,
    )
    assert [e["titles"] for e in unsaved["events"]] == [["Dienst: Theke"]]
    assert unsaved["events"][0]["all_day"] is False

    broken = await client.ok("preview", rule={"sources": ["calendar.nope"]})
    assert broken["events"] == []
    assert broken["errors"] == {"calendar.nope": "calendar not found"}

    error = await client.error("preview", rule={"sources": []})
    assert error["code"] == "invalid_format"
    assert (await client.error("preview", rule_id="nope"))["code"] == "not_found"
    assert (await client.error("preview"))["code"] == "invalid_format"
