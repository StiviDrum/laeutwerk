"""Repair issues for missing entities and actions."""

from __future__ import annotations

from datetime import date

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.laeutwerk.const import DOMAIN
from custom_components.laeutwerk.issues import (
    issue_id,
    rule_action_refs,
    rule_entity_refs,
)
from custom_components.laeutwerk.model import Rule
from custom_components.laeutwerk.schema import validate_rule

from .common import PHONE, WASTE, FakeCalendars, at, muell_rule, setup_integration
from .ha_testing import async_mock_service

LAMP = "light.stehleuchte"
DOOR = "binary_sensor.haustuer"


def full_rule() -> dict:
    return muell_rule(
        signals=[
            {
                "id": "push",
                "type": "notify",
                "targets": [PHONE],
                "message": "x",
                "conditions": [
                    {
                        "condition": "state",
                        "entity_id": "input_boolean.urlaub",
                        "state": "off",
                    }
                ],
            },
            {
                "id": "lampe",
                "type": "light_signal",
                "entity": LAMP,
                "when": {
                    "opportunity": {"trigger": "state", "entity_id": LAMP, "to": "on"}
                },
            },
            {
                "id": "ansage",
                "type": "announce",
                "players": ["media_player.sonos"],
                "tts": "tts.piper",
                "text": "x",
            },
            {
                "id": "eigene",
                "type": "action",
                "actions": [
                    {"action": "light.turn_on", "target": {"entity_id": "{{ lampe }}"}},
                    {"action": "scene.turn_on", "target": {"entity_id": "scene.abend"}},
                ],
            },
        ],
        acknowledge=[
            {"type": "trigger", "trigger": {"trigger": "state", "entity_id": DOOR}}
        ],
        activation={
            "conditions": [
                {
                    "condition": "state",
                    "entity_id": "input_boolean.abwesend",
                    "state": "off",
                }
            ]
        },
        on_done=[
            {"action": "counter.increment", "target": {"entity_id": "counter.tonnen"}}
        ],
        assignee={"persons": ["person.steven"]},
    )


def test_rule_refs() -> None:
    rule = Rule.from_dict(validate_rule(full_rule()))
    assert rule_entity_refs(rule) == {
        WASTE,
        "input_boolean.urlaub",
        LAMP,
        "media_player.sonos",
        "tts.piper",
        "scene.abend",
        DOOR,
        "input_boolean.abwesend",
        "counter.tonnen",
        "person.steven",
    }
    assert rule_action_refs(rule) == {PHONE}


async def test_issue_created_and_resolved(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(at(date(2026, 11, 16), 9))
    FakeCalendars(hass, WASTE)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule(sources=[WASTE, "calendar.weg"]))
    await hass.async_block_till_done()

    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id("muell"))
    assert issue is not None
    assert issue.translation_key == "missing_entities"
    assert issue.translation_placeholders == {
        "rule": "Müll rausstellen",
        "entities": f"calendar.weg, {PHONE}",
    }

    # The phone app gets set up and the calendar appears: issue gone.
    async_mock_service(hass, "notify", PHONE.split(".")[1])
    hass.states.async_set("calendar.weg", "off")
    manager._async_registry_updated(None)  # what an entity registry update does
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id("muell")) is None

    # Disabled rules and deleted rules have no issue.
    hass.states.async_remove("calendar.weg")
    manager._async_registry_updated(None)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id("muell"))
    await manager.async_set_enabled("muell", False)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id("muell")) is None
    await manager.async_set_enabled("muell", True)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id("muell"))
    await manager.async_delete_rule("muell")
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id("muell")) is None
