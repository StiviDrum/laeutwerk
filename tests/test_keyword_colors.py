"""Own colour per keyword (0.7.5): storage, card dots, light signal."""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
import pytest

from custom_components.laeutwerk import signals
from custom_components.laeutwerk.compat import vol
from custom_components.laeutwerk.matching import keyword_colors, parse_event
from custom_components.laeutwerk.model import Rule
from custom_components.laeutwerk.schema import validate_rule

from .common import TZ, WASTE, FakeCalendars, at, muell_rule, setup_integration, tick
from .ha_testing import async_mock_service

MON = date(2026, 11, 16)
TUE = date(2026, 11, 17)
LAMP = "light.stehleuchte"


def colored_rule(**changes: Any) -> dict[str, Any]:
    return muell_rule(
        filter={
            "all_day": True,
            "keywords": {
                "columns": ["tonne"],
                "rows": [
                    {"match": "Papier", "tonne": "Papiertonne", "color": "#0000FF"},
                    {"match": "Bio", "tonne": "Biotonne", "color": "#8b4513"},
                    {"match": "Rest", "tonne": "Restmülltonne"},
                ],
            },
        },
        **changes,
    )


def events(*titles: str):
    return [
        parse_event(
            WASTE, {"start": "2026-11-17", "end": "2026-11-18", "summary": t}, TZ
        )
        for t in titles
    ]


def test_stored_colour_and_dots() -> None:
    data = validate_rule(colored_rule())
    rows = data["filter"]["keywords"]["rows"]
    assert rows[0] == {"match": "Papier", "color": "#0000ff", "tonne": "Papiertonne"}
    assert "color" not in rows[2]
    rule = Rule.from_dict(data)
    assert rule.filter.rows[0].color == "#0000ff"
    assert rule.to_dict()["filter"]["keywords"]["rows"] == rows
    assert keyword_colors(rule, events("Papier", "Bio")) == ["#0000ff", "#8b4513"]
    assert keyword_colors(rule, events("Rest")) == []


def test_invalid_colour() -> None:
    with pytest.raises(vol.Invalid, match="keyword row 1: 'blau' is not a colour"):
        validate_rule(
            muell_rule(
                filter={"keywords": {"rows": [{"match": "Papier", "color": "blau"}]}}
            )
        )


@pytest.fixture(autouse=True)
def no_sleep():
    async def instantly(_seconds: float) -> None:
        return None

    with patch.object(signals, "_sleep", instantly):
        yield


async def test_light_alternates_the_keyword_colours(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    turn_on = async_mock_service(hass, "light", "turn_on")
    async_mock_service(hass, "light", "turn_off")
    hass.states.async_set(LAMP, "off", {"supported_color_modes": ["hs"]})
    freezer.move_to(at(MON, 9))
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", TUE)
    calendars.add_all_day(WASTE, "Bio", TUE)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(
        colored_rule(
            signals=[
                {
                    "id": "lampe",
                    "type": "light_signal",
                    "entity": LAMP,
                    "pattern": {"count": 3},
                    "color_from_keyword": True,
                    "color": "#ffffff",
                }
            ]
        )
    )
    await tick(hass, freezer, at(MON, 17, 0))
    # Bundle Bio + Papier: blue, brown, blue (bundle order: Bio, Papier).
    blinks = [c.data["rgb_color"] for c in turn_on if "rgb_color" in c.data]
    assert blinks == [[139, 69, 19], [0, 0, 255], [139, 69, 19]]


async def test_light_without_keyword_colours_uses_the_fixed_colour(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    turn_on = async_mock_service(hass, "light", "turn_on")
    async_mock_service(hass, "light", "turn_off")
    hass.states.async_set(LAMP, "off", {"supported_color_modes": ["hs"]})
    freezer.move_to(at(MON, 9))
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Rest", TUE)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(
        colored_rule(
            signals=[
                {
                    "id": "lampe",
                    "type": "light_signal",
                    "entity": LAMP,
                    "pattern": {"count": 2},
                    "color_from_keyword": True,
                    "color": "#ff0000",
                }
            ]
        )
    )
    await tick(hass, freezer, at(MON, 17, 0))
    blinks = [c.data["rgb_color"] for c in turn_on if "rgb_color" in c.data]
    assert blinks == [[255, 0, 0], [255, 0, 0]]
