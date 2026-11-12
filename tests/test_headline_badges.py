"""Keyword icon, editable headline and badges in the payloads."""

from __future__ import annotations

from datetime import date
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
import pytest

from custom_components.laeutwerk.compat import vol
from custom_components.laeutwerk.manager import LaeutwerkManager
from custom_components.laeutwerk.matching import (
    hit_badges,
    parse_event,
    render_headline,
)
from custom_components.laeutwerk.model import Rule
from custom_components.laeutwerk.schema import validate_rule

from .common import TZ, WASTE, FakeCalendars, at, muell_rule, setup_integration
from .ha_testing import WebSocketGenerator, async_mock_service

MON = date(2026, 11, 16)
TUE = date(2026, 11, 17)


def events(*titles: str):
    return [
        parse_event(
            WASTE, {"start": "2026-11-17", "end": "2026-11-18", "summary": t}, TZ
        )
        for t in titles
    ]


def rule_data(**changes: Any) -> dict[str, Any]:
    """Bio: own icon + colour; Papier: colour only; Rest: nothing."""
    return muell_rule(
        filter={
            "all_day": True,
            "keywords": {
                "columns": ["tonne"],
                "rows": [
                    {
                        "match": "Papier",
                        "tonne": "Papiertonne",
                        "color": "#0000ff",
                    },
                    {
                        "match": "Bio",
                        "icon": "mdi:leaf",
                        "color": "#8b4513",
                        "tonne": "Biotonne",
                    },
                    {"match": "Rest", "tonne": "Restmülltonne"},
                ],
            },
        },
        **changes,
    )


def test_icon_validation_and_round_trip() -> None:
    data = validate_rule(rule_data())
    rows = data["filter"]["keywords"]["rows"]
    assert rows[1]["icon"] == "mdi:leaf"
    assert "icon" not in rows[0]
    rule = Rule.from_dict(data)
    assert rule.filter.rows[1].icon == "mdi:leaf"
    assert rule.filter.rows[0].icon is None
    assert rule.to_dict()["filter"]["keywords"]["rows"] == rows


def test_empty_icon_is_omitted_and_invalid_rejected() -> None:
    data = validate_rule(
        muell_rule(
            filter={"keywords": {"rows": [{"match": "Papier", "icon": ""}]}},
        )
    )
    assert "icon" not in data["filter"]["keywords"]["rows"][0]
    with pytest.raises(vol.Invalid, match="keyword row 1: icon must look like"):
        validate_rule(
            muell_rule(
                filter={"keywords": {"rows": [{"match": "Papier", "icon": "recycle"}]}}
            )
        )


def test_headline_round_trip() -> None:
    data = validate_rule(rule_data(headline="{wann}: {tonne}"))
    assert data["headline"] == "{wann}: {tonne}"
    rule = Rule.from_dict(data)
    assert rule.to_dict()["headline"] == "{wann}: {tonne}"
    assert Rule.from_dict(validate_rule(rule_data())).headline is None


def test_headline_rendering() -> None:
    rule = Rule.from_dict(validate_rule(rule_data(headline="{wann}: {tonne}")))
    two = events("Papier", "Bio")
    assert render_headline(rule, two, {"wann": "morgen", "tonne": "x"}) == ("Morgen: x")
    assert render_headline(rule, two, {"wann": "morgen", "tonne": "x"}) == ("Morgen: x")
    rule.headline = None
    assert render_headline(rule, two, {}) is None


def test_badges() -> None:
    rule = Rule.from_dict(validate_rule(rule_data()))
    assert hit_badges(rule, events("Papier", "Bio")) == [
        {"icon": None, "color": "#0000ff"},
        {"icon": "mdi:leaf", "color": "#8b4513"},
    ]
    assert hit_badges(rule, events("Rest")) == [{"icon": None, "color": None}]
    # Identical pairs are removed.
    assert hit_badges(rule, events("Rest", "Rest")) == [{"icon": None, "color": None}]
    plain = Rule.from_dict(validate_rule(muell_rule(filter={"all_day": True})))
    assert hit_badges(plain, events("Papier")) == []


@pytest.fixture
async def manager(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> LaeutwerkManager:
    freezer.move_to(at(MON, 9))
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", TUE)
    calendars.add_all_day(WASTE, "Bio", TUE)
    async_mock_service(hass, "notify", "mobile_app_steven")
    _, manager = await setup_integration(hass)
    return manager


async def test_payloads_sensor_and_preview(
    hass: HomeAssistant,
    manager: LaeutwerkManager,
    hass_ws_client: WebSocketGenerator,
) -> None:
    await manager.async_create_rule(rule_data(headline="{wann}: {tonnen}"))
    await hass.async_block_till_done()

    expected = [
        {"icon": "mdi:leaf", "color": "#8b4513"},
        {"icon": None, "color": "#0000ff"},
    ]
    status = manager.status("muell")
    reminder = status["reminders"][0]
    assert reminder["headline"] == "Morgen: Biotonne und Papiertonne"
    assert reminder["badges"] == expected
    assert status["next_event"]["headline"] == "Morgen: Biotonne und Papiertonne"
    assert status["next_event"]["badges"] == expected

    state = hass.states.get("sensor.laeutwerk_muell")
    assert state is not None
    assert state.attributes["headline"] == "Morgen: Biotonne und Papiertonne"

    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "laeutwerk/preview", "rule_id": "muell"})
    msg = await ws.receive_json()
    assert msg["success"], msg
    first = msg["result"]["events"][0]
    assert first["headline"] == "Morgen: Biotonne und Papiertonne"
    assert first["badges"] == expected


async def test_no_headline_gives_none(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(at(MON, 9))
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", TUE)
    async_mock_service(hass, "notify", "mobile_app_steven")
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await hass.async_block_till_done()
    assert manager.status("muell")["reminders"][0]["headline"] is None
    state = hass.states.get("sensor.laeutwerk_muell")
    assert state is not None
    assert state.attributes["headline"] is None
