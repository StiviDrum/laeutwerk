"""Signal types, audience, quiet times, limits, conditions and test_signal."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
import pytest

from custom_components.laeutwerk import signals
from custom_components.laeutwerk.colors import parse_color
from custom_components.laeutwerk.compat import vol
from custom_components.laeutwerk.manager import LaeutwerkManager
from custom_components.laeutwerk.model import Signal
from custom_components.laeutwerk.schema import validate_signal

from .common import (
    PHONE,
    TZ,
    WASTE,
    FakeCalendars,
    at,
    muell_rule,
    setup_integration,
    tick,
)
from .ha_testing import MockConfigEntry, async_mock_service

MON = date(2026, 11, 16)
TUE = date(2026, 11, 17)
LAMP = "light.stehleuchte"
SONOS = "media_player.sonos_wohnzimmer"
REMINDER = "muell__20261117"

PUSH = {"id": "push", "type": "notify", "targets": [PHONE], "message": "{tonnen}"}
LIGHT = {
    "id": "lampe",
    "type": "light_signal",
    "entity": LAMP,
    "pattern": {"effect": "blink", "count": 2},
    "color_from": "farbe",
}
ANNOUNCE = {
    "id": "ansage",
    "type": "announce",
    "players": [SONOS],
    "volume": 45,
    "tts": "tts.piper",
    "text": "Stell endlich die {tonne} raus!",
    "text_plural": "Stell endlich {tonnen} raus!",
}


@pytest.fixture(autouse=True)
def no_sleep():
    async def instantly(_seconds: float) -> None:
        return None

    with patch.object(signals, "_sleep", instantly):
        yield


@pytest.fixture
def pushes(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "notify", PHONE.split(".")[1])


async def start(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    *signal_list: dict[str, Any],
    titles: tuple[str, ...] = ("Papier",),
    **changes: Any,
) -> LaeutwerkManager:
    """Monday 09:00, event(s) on Tuesday, reminder Monday 17:00."""
    freezer.move_to(at(MON, 9))
    calendars = FakeCalendars(hass, WASTE)
    for title in titles:
        calendars.add_all_day(WASTE, title, TUE)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule(signals=list(signal_list), **changes))
    await hass.async_block_till_done()
    return manager


# ------------------------------------------------------------------ pure parts


def test_parse_color() -> None:
    assert parse_color("blau") == (0, 0, 255)
    assert parse_color(" Grün ") == (0, 128, 0)
    assert parse_color("gelb") == (255, 255, 0)
    assert parse_color("grau") == (255, 255, 255)  # a lamp cannot shine grey
    assert parse_color("#ff8800") == (255, 136, 0)
    assert parse_color("00FF00") == (0, 255, 0)
    assert parse_color("255, 0, 10") == (255, 0, 10)
    assert parse_color("300,0,0") is None
    assert parse_color("dark orange") == (255, 140, 0)
    assert parse_color("kariert") is None
    assert parse_color("") is None
    assert parse_color(None) is None


def test_quiet_until() -> None:
    signal = Signal.from_dict(
        validate_signal(
            {
                **PUSH,
                "quiet": [
                    {"from": "22:00", "to": "8:00", "mode": "defer"},
                    {"from": "12:00", "to": "13:30"},
                ],
            }
        )
    )

    def quiet(hour: int, minute: int = 0, day: date = MON):
        return signals.quiet_until(signal, at(day, hour, minute), TZ)

    assert quiet(9) is None
    assert quiet(8) is None  # the end is exclusive
    assert quiet(21, 59) is None
    assert quiet(12) == ("skip", datetime(2026, 11, 16, 12, 30, tzinfo=UTC))
    assert quiet(13, 29) == ("skip", datetime(2026, 11, 16, 12, 30, tzinfo=UTC))
    assert quiet(13, 30) is None
    # Across midnight: before and after it.
    assert quiet(22) == ("defer", datetime(2026, 11, 17, 7, 0, tzinfo=UTC))
    assert quiet(3, 15) == ("defer", datetime(2026, 11, 16, 7, 0, tzinfo=UTC))
    # Night of the clock change: 08:00 is CEST on Sunday (06:00 UTC).
    assert quiet(23, day=date(2026, 3, 28)) == (
        "defer",
        datetime(2026, 3, 29, 6, 0, tzinfo=UTC),
    )


def test_signal_validation() -> None:
    light = validate_signal(LIGHT)
    assert light["entities"] == [LAMP]
    assert "entity" not in light
    assert light["pattern"] == {"effect": "blink", "count": 2, "interval": 0.8}
    assert light["restore"] is True
    assert validate_signal(ANNOUNCE)["volume"] == 45
    custom = validate_signal(
        {"type": "action", "actions": {"action": "scene.turn_on", "target": {}}}
    )
    assert custom["actions"] == [{"action": "scene.turn_on", "target": {}}]

    def invalid(config: dict[str, Any], message: str) -> None:
        with pytest.raises(Exception, match=message):
            validate_signal(config)

    invalid({"type": "notify", "message": "x"}, "'targets' or an 'audience'")
    invalid(
        {"type": "notify", "message": "x", "audience": "persons"}, "list of 'persons'"
    )
    invalid({**LIGHT, "entity": "switch.x"}, "not a light entity")
    invalid({**LIGHT, "pattern": {"count": 99}}, "count")
    invalid({**ANNOUNCE, "players": []}, "length")
    invalid({**ANNOUNCE, "volume": 150}, "volume")
    invalid({"type": "action", "actions": []}, "at least one action")
    invalid({"type": "action", "actions": [{"foo": "bar"}]}, "action")
    invalid({**PUSH, "quiet": [{"from": "25:00", "to": "08:00"}]}, "time of day")
    invalid({**PUSH, "quiet": [{"from": "22:00", "to": "08:00", "mode": "x"}]}, "mode")
    invalid({**PUSH, "limit": {"per_reminder": 0}}, "per_reminder")


async def test_conditions_and_actions_are_checked_on_save(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    manager = await start(hass, freezer)
    for broken in (
        {**PUSH, "conditions": [{"condition": "nonsense"}]},
        {**PUSH, "conditions": [{"condition": "state", "entity_id": "light.x"}]},
        {"id": "push", "type": "action", "actions": [{"action": "kein dienst"}]},
    ):
        with pytest.raises(vol.Invalid):
            await manager.async_update_rule("muell", muell_rule(signals=[broken]))
    assert manager.rules["muell"].signals == []


async def test_color_from_must_be_a_column(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    manager = await start(hass, freezer)
    with pytest.raises(Exception, match="color_from 'bunt' is not a column"):
        await manager.async_update_rule(
            "muell", muell_rule(signals=[{**LIGHT, "color_from": "bunt"}])
        )


# ----------------------------------------------------------------------- light


async def test_light_signal_blinks_in_column_colour_and_restores(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    turn_on = async_mock_service(hass, "light", "turn_on")
    turn_off = async_mock_service(hass, "light", "turn_off")
    hass.states.async_set(
        LAMP,
        "on",
        {
            "brightness": 180,
            "color_mode": "color_temp",
            "color_temp_kelvin": 2700,
            "supported_color_modes": ["color_temp", "hs"],
        },
    )
    await start(hass, freezer, LIGHT)
    await tick(hass, freezer, at(MON, 17, 0))

    blink = {
        "entity_id": LAMP,
        "brightness_pct": 100,
        "transition": 0,
        "rgb_color": [0, 0, 255],  # Papier -> farbe "blau"
    }
    assert [call.data for call in turn_on] == [
        blink,
        blink,
        # Exactly the state from before.
        {
            "entity_id": LAMP,
            "transition": 0,
            "brightness": 180,
            "color_temp_kelvin": 2700,
        },
    ]
    assert [call.data for call in turn_off] == [{"entity_id": LAMP}] * 2


async def test_light_signal_on_a_lamp_that_was_off(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    turn_on = async_mock_service(hass, "light", "turn_on")
    turn_off = async_mock_service(hass, "light", "turn_off")
    hass.states.async_set(LAMP, "off", {"supported_color_modes": ["brightness"]})
    signal = {
        **LIGHT,
        "color": "rot",
        "color_from": None,
        "brightness": 60,
        "pattern": {"effect": "pulse", "count": 1, "interval": 1.5},
    }
    del signal["color_from"]
    await start(hass, freezer, signal)
    await tick(hass, freezer, at(MON, 17, 0))

    # No colour for a lamp without colour; pulse dims instead of switching off.
    high = {"entity_id": LAMP, "brightness_pct": 60, "transition": 1.5}
    assert [call.data for call in turn_on] == [high, {**high, "brightness_pct": 8}]
    assert [call.data for call in turn_off] == [{"entity_id": LAMP, "transition": 0}]


async def test_light_signal_without_restore_and_missing_lamp(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    turn_on = async_mock_service(hass, "light", "turn_on")
    async_mock_service(hass, "light", "turn_off")
    hass.states.async_set(LAMP, "off", {"supported_color_modes": ["rgb"]})
    manager = await start(
        hass,
        freezer,
        {**LIGHT, "entity": [LAMP, "light.gibt_es_nicht"], "restore": False},
    )
    events: list = []

    @callback
    def capture(event) -> None:
        events.append(event)

    hass.bus.async_listen("laeutwerk_signal_sent", capture)
    await tick(hass, freezer, at(MON, 17, 0))
    # Stays on in the signal colour; the missing lamp does not break anything.
    assert len(turn_on) == 3
    assert turn_on[-1].data["rgb_color"] == [0, 0, 255]
    assert len(events) == 1
    assert manager.reminders["muell"][REMINDER].signals_sent == {"lampe": 1}


# ---------------------------------------------------- announcement and action


async def test_announcement(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    play = async_mock_service(hass, "media_player", "play_media")
    with patch.object(
        signals,
        "_media_source_id",
        side_effect=lambda hass, message, **kw: f"tts:{kw['engine']}:{message}",
    ):
        await start(hass, freezer, ANNOUNCE, titles=("Papier", "Bio"))
        await tick(hass, freezer, at(MON, 17, 0))
    assert [call.data for call in play] == [
        {
            "entity_id": [SONOS],
            "media_content_id": "tts:tts.piper:Stell endlich Biotonne und "
            "Papiertonne raus!",
            "media_content_type": "music",
            "announce": True,
            "extra": {"volume": 45},
        }
    ]


async def test_announcement_without_tts_is_not_sent(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    play = async_mock_service(hass, "media_player", "play_media")
    manager = await start(hass, freezer, ANNOUNCE)
    await tick(hass, freezer, at(MON, 17, 0))
    assert not play
    assert manager.status("muell")["state"] == "reminded"


async def test_custom_action_gets_the_variables(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    calls = async_mock_service(hass, "test", "do")
    await start(
        hass,
        freezer,
        {
            "type": "action",
            "actions": [
                {
                    "action": "test.do",
                    "data": {
                        "text": "{{ wann }}: {{ tonnen }}",
                        "id": "{{ reminder_id }}",
                        "many": "{{ plural }}",
                    },
                }
            ],
        },
        titles=("Papier", "Gelb"),
    )
    await tick(hass, freezer, at(MON, 17, 0))
    assert [call.data for call in calls] == [
        {
            "text": "morgen: gelben Sack und Papiertonne",
            "id": REMINDER,
            "many": True,
        }
    ]


# -------------------------------------------------------------------- audience


async def test_audience(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    registry = er.async_get(hass)
    phones: dict[str, list[ServiceCall]] = {}
    for person, device, where in (
        ("steven", "Stevens Handy", "home"),
        ("anna", "Annas iPhone", "not_home"),
    ):
        entry = MockConfigEntry(domain="mobile_app", data={"device_name": device})
        entry.add_to_hass(hass)
        tracker = registry.async_get_or_create(
            "device_tracker", "mobile_app", person, config_entry=entry
        )
        hass.states.async_set(
            f"person.{person}",
            where,
            {"device_trackers": [tracker.entity_id, "device_tracker.router"]},
        )
        service = f"mobile_app_{device.lower().replace(' ', '_')}"
        phones[person] = async_mock_service(hass, "notify", service)

    def signal(audience: str, **extra: Any) -> dict[str, Any]:
        return {"type": "notify", "message": "x", "audience": audience, **extra}

    manager = await start(
        hass,
        freezer,
        signal("present", id="present"),
        signal("all", id="all", targets=[PHONE]),
        signal("persons", id="persons", persons=["person.anna", "person.niemand"]),
    )
    await tick(hass, freezer, at(MON, 17, 0))
    assert len(phones["steven"]) == 2  # present + all
    assert len(phones["anna"]) == 2  # all + persons
    assert len(pushes) == 1  # explicit target in addition to the audience

    # Clearing reaches the same phones.
    await manager.async_acknowledge("muell")
    await hass.async_block_till_done()
    assert [c.data["message"] for c in phones["steven"][2:]] == [
        "clear_notification"
    ] * 2


# ------------------------------------------------- quiet times, limits, only if


async def test_quiet_time_skip_and_defer(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    quiet = {"from": "16:00", "to": "18:30"}
    manager = await start(
        hass,
        freezer,
        {**PUSH, "id": "skipped", "message": "skipped", "quiet": [quiet]},
        {
            **PUSH,
            "id": "later",
            "message": "later",
            "quiet": [{**quiet, "mode": "defer"}],
        },
        {**PUSH, "id": "direct", "message": "direct"},
    )
    await tick(hass, freezer, at(MON, 17, 0))
    assert [call.data["message"] for call in pushes] == ["direct"]
    reminder = manager.reminders["muell"][REMINDER]
    assert list(reminder.deferred) == ["later"]

    await tick(hass, freezer, at(MON, 18, 29))
    assert len(pushes) == 1
    await tick(hass, freezer, at(MON, 18, 30))
    assert [call.data["message"] for call in pushes] == ["direct", "later"]
    assert reminder.deferred == {}
    assert reminder.signals_sent == {"direct": 1, "later": 1}
    await tick(hass, freezer, at(MON, 20, 0))
    assert len(pushes) == 2


async def test_deferred_signal_survives_restart_and_stops_with_acknowledge(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    quiet = [{"from": "16:00", "to": "18:30", "mode": "defer"}]
    freezer.move_to(at(MON, 9))
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", TUE)
    calendars.add_all_day(WASTE, "Bio", date(2026, 11, 23))
    entry, manager = await setup_integration(hass)
    await manager.async_create_rule(
        muell_rule(signals=[{**PUSH, "quiet": quiet}], reminders=[{"at": "-1d 17:00"}])
    )
    await tick(hass, freezer, at(MON, 17, 0))
    assert not pushes

    assert await hass.config_entries.async_unload(entry.entry_id)
    freezer.move_to(at(MON, 19, 0))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert [call.data["message"] for call in pushes] == ["Papiertonne"]

    # Next week: acknowledged during the quiet time -> nothing is sent later.
    manager = entry.runtime_data
    await tick(hass, freezer, at(date(2026, 11, 22), 17, 0))
    assert manager.status("muell")["state"] == "reminded"
    await manager.async_acknowledge("muell")
    await tick(hass, freezer, at(date(2026, 11, 22), 18, 30))
    sent = [c.data["message"] for c in pushes]
    assert [message for message in sent if message != "clear_notification"] == [
        "Papiertonne"
    ]


async def test_limits(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    await start(
        hass,
        freezer,
        {**PUSH, "id": "once", "message": "once", "limit": {"per_reminder": 1}},
        {**PUSH, "id": "spaced", "message": "spaced", "limit": {"min_interval": 90}},
        {**PUSH, "id": "always", "message": "always"},
        reminders=[{"at": "-1d 17:00"}, {"at": "-1d 18:00"}, {"at": "-1d 19:00"}],
    )
    await tick(hass, freezer, at(MON, 17, 0))
    await tick(hass, freezer, at(MON, 18, 0))
    await tick(hass, freezer, at(MON, 19, 0))
    assert [call.data["message"] for call in pushes] == [
        *("once", "spaced", "always"),
        "always",  # 18:00: "spaced" was sent 60 min ago
        *("spaced", "always"),
    ]


async def test_only_if_conditions(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    def condition(entity_id: str) -> dict[str, str]:
        return {"condition": "state", "entity_id": entity_id, "state": "on"}

    both = [condition("input_boolean.a"), condition("input_boolean.b")]
    hass.states.async_set("input_boolean.a", "on")
    hass.states.async_set("input_boolean.b", "off")
    manager = await start(
        hass,
        freezer,
        {**PUSH, "id": "all", "message": "all", "conditions": both},
        {
            **PUSH,
            "id": "any",
            "message": "any",
            "conditions": both,
            "conditions_match": "any",
        },
        reminders=[{"at": "-1d 17:00"}, {"at": "-1d 18:00"}],
    )
    await tick(hass, freezer, at(MON, 17, 0))
    assert [call.data["message"] for call in pushes] == ["any"]
    # Not sent = not counted.
    assert manager.reminders["muell"][REMINDER].signals_sent == {"any": 1}

    hass.states.async_set("input_boolean.b", "on")
    await tick(hass, freezer, at(MON, 18, 0))
    assert sorted(call.data["message"] for call in pushes[1:]) == ["all", "any"]


async def test_disabled_signal_is_not_sent(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    await start(hass, freezer, {**PUSH, "enabled": False})
    await tick(hass, freezer, at(MON, 17, 0))
    assert not pushes


# ----------------------------------------------------------------- test_signal


async def test_test_signal_service(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    quiet = [{"from": "00:00", "to": "23:59"}]
    manager = await start(
        hass,
        freezer,
        {**PUSH, "quiet": quiet, "actions": [{"ack": True, "label": "ok"}]},
    )

    async def test(**data: Any) -> None:
        await hass.services.async_call(
            "laeutwerk", "test_signal", {"rule": "muell", **data}, blocking=True
        )

    # A saved signal, for the next real event; quiet time is ignored.
    await test(signal="push")
    assert pushes[0].data["message"] == "Papiertonne"
    assert pushes[0].data["data"]["tag"] == "laeutwerk_test"
    # Nothing is counted and the reminder is untouched.
    reminder = manager.reminders["muell"][REMINDER]
    assert reminder.state == "planned"
    assert reminder.signals_sent == {}

    # An unsaved signal.
    await test(
        config={"type": "notify", "targets": [PHONE], "message": "{wann} {farbe}"}
    )
    assert pushes[1].data["message"] == "Morgen blau"

    # Without any event a sample for tomorrow is used (first keyword row).
    await manager.async_update_rule(
        "muell", muell_rule(sources=["calendar.leer"], signals=[PUSH])
    )
    await test(signal="push")
    assert pushes[2].data["message"] == "Papiertonne"

    with pytest.raises(ServiceValidationError):
        await test(signal="gibt_es_nicht")
    with pytest.raises(ServiceValidationError):
        await test()
    with pytest.raises(ServiceValidationError):
        await test(signal="push", config=PUSH)
    with pytest.raises(ServiceValidationError, match="unknown signal type"):
        await test(config={"type": "fax"})
    with pytest.raises(HomeAssistantError):
        await test(
            config={"type": "notify", "targets": ["notify.nobody"], "message": "x"}
        )


async def _persons(hass: HomeAssistant) -> dict[str, list[ServiceCall]]:
    """Steven (phone, home), Anna (phone, away), Gast (no app, home)."""
    registry = er.async_get(hass)
    phones: dict[str, list[ServiceCall]] = {}
    for person, device, where in (
        ("steven", "Stevens Handy", "home"),
        ("anna", "Annas iPhone", "not_home"),
        ("gast", None, "home"),
    ):
        trackers = []
        if device:
            entry = MockConfigEntry(domain="mobile_app", data={"device_name": device})
            entry.add_to_hass(hass)
            trackers.append(
                registry.async_get_or_create(
                    "device_tracker", "mobile_app", person, config_entry=entry
                ).entity_id
            )
            service = f"mobile_app_{device.lower().replace(' ', '_')}"
            phones[person] = async_mock_service(hass, "notify", service)
        hass.states.async_set(
            f"person.{person}",
            where,
            {"friendly_name": person.capitalize(), "device_trackers": trackers},
        )
    return phones


async def test_chosen_persons_only_when_home(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    phones = await _persons(hass)
    chosen = ["person.steven", "person.anna"]
    await start(
        hass,
        freezer,
        {
            "type": "notify",
            "message": "x",
            "audience": "persons",
            "persons": chosen,
            "id": "a",
        },
        {
            "type": "notify",
            "message": "y",
            "audience": "persons",
            "persons": chosen,
            "only_present": True,
            "id": "b",
        },
    )
    await tick(hass, freezer, at(MON, 17, 0))
    assert sorted(c.data["message"] for c in phones["steven"]) == ["x", "y"]
    assert [c.data["message"] for c in phones["anna"]] == ["x"]


async def test_persons_websocket(hass: HomeAssistant, hass_ws_client) -> None:
    await _persons(hass)
    await setup_integration(hass)
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "laeutwerk/persons"})
    result = (await ws.receive_json())["result"]["persons"]
    assert result == [
        {
            "entity_id": "person.anna",
            "name": "Anna",
            "state": "not_home",
            "notify": ["notify.mobile_app_annas_iphone"],
        },
        {"entity_id": "person.gast", "name": "Gast", "state": "home", "notify": []},
        {
            "entity_id": "person.steven",
            "name": "Steven",
            "state": "home",
            "notify": ["notify.mobile_app_stevens_handy"],
        },
    ]
