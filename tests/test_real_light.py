"""Light signal against a real (template) light: blink, restore, no self-trigger."""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.setup import async_setup_component

from custom_components.laeutwerk import signals

from .common import WASTE, FakeCalendars, at, muell_rule, setup_integration, tick

MON = date(2026, 11, 16)
TUE = date(2026, 11, 17)
LAMP = "light.stehleuchte"


def _set(entity_id: str, value: str) -> dict:
    return {
        "action": "input_number.set_value",
        "target": {"entity_id": entity_id},
        "data": {"value": value},
    }


_ON = {
    "action": "input_boolean.turn_on",
    "target": {"entity_id": "input_boolean.lamp"},
}

TEMPLATE_LIGHT = {
    "name": "Stehleuchte",
    "state": "{{ is_state('input_boolean.lamp', 'on') }}",
    "level": "{{ states('input_number.level') | int(0) }}",
    "hs": (
        "{{ (states('input_number.hue') | int(0),"
        " states('input_number.sat') | int(0)) }}"
    ),
    "turn_on": [_ON],
    "turn_off": [
        {
            "action": "input_boolean.turn_off",
            "target": {"entity_id": "input_boolean.lamp"},
        }
    ],
    "set_level": [_set("input_number.level", "{{ brightness }}"), _ON],
    "set_hs": [
        _set("input_number.hue", "{{ h | int }}"),
        _set("input_number.sat", "{{ s | int }}"),
        _ON,
    ],
}


async def setup_lamp(hass: HomeAssistant) -> None:
    number = {"min": 0, "max": 360, "step": 1}
    assert await async_setup_component(
        hass, "input_boolean", {"input_boolean": {"lamp": {"initial": False}}}
    )
    assert await async_setup_component(
        hass,
        "input_number",
        {
            "input_number": {
                "level": {**number, "initial": 180},
                "hue": {**number, "initial": 30},
                "sat": {**number, "initial": 40},
            }
        },
    )
    assert await async_setup_component(
        hass, "template", {"template": [{"light": [TEMPLATE_LIGHT]}]}
    )
    await hass.async_block_till_done()
    assert hass.states.get(LAMP).state == "off"


async def test_blink_on_manual_switch_on_and_restore(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, hass_admin_user
) -> None:
    """SPEC B8: the lamp blinks when someone switches it on, then is normal."""
    freezer.move_to(at(MON, 9))
    await setup_lamp(hass)
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", TUE)

    seen: list[tuple[str, tuple | None]] = []

    @callback
    def record(event) -> None:
        state = event.data["new_state"]
        if state.entity_id == LAMP:
            seen.append((state.state, state.attributes.get("hs_color")))

    hass.bus.async_listen("state_changed", record)
    sent: list = []

    @callback
    def signal_sent(event) -> None:
        sent.append(event)

    hass.bus.async_listen("laeutwerk_signal_sent", signal_sent)

    async def instantly(_seconds: float) -> None:
        # Let the lamp's state changes arrive (block_till_done would wait
        # for the signal task itself).
        for _ in range(20):
            await asyncio.sleep(0)

    _, manager = await setup_integration(hass)
    await manager.async_create_rule(
        muell_rule(
            signals=[
                {
                    "id": "lampe",
                    "type": "light_signal",
                    "entity": LAMP,
                    "pattern": {"effect": "blink", "count": 3},
                    "color_from": "farbe",
                    "when": {
                        "opportunity": {
                            "trigger": "state",
                            "entity_id": LAMP,
                            "to": "on",
                        },
                        "manual_only": True,
                    },
                    "restore": True,
                }
            ]
        )
    )
    await tick(hass, freezer, at(MON, 17, 0))
    assert not sent

    with patch.object(signals, "_sleep", instantly):
        await hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": LAMP},
            blocking=True,
            context=Context(user_id=hass_admin_user.id),
        )
        for _ in range(5):
            await hass.async_block_till_done()

    # It blinked blue three times and never triggered itself again.
    assert len(sent) == 1
    assert manager.reminders["muell"]["muell__20261117"].signals_sent == {"lampe": 1}
    blue = [entry for entry in seen if entry == ("on", (240.0, 100.0))]
    assert len(blue) >= 3
    assert sum(1 for entry in seen if entry[0] == "off") == 3

    # Afterwards the lamp is on exactly as the person switched it on.
    state = hass.states.get(LAMP)
    assert state.state == "on"
    assert state.attributes["brightness"] == 180
    assert state.attributes["hs_color"] == (30.0, 40.0)
