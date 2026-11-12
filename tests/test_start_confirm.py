"""0.9: start triggers, confirmation, household quiet time."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
import pytest

from custom_components.laeutwerk.compat import vol
from custom_components.laeutwerk.const import DOMAIN
from custom_components.laeutwerk.manager import LaeutwerkManager
from custom_components.laeutwerk.schema import validate_rule

from .common import PHONE, at, setup_integration, tick
from .ha_testing import WebSocketGenerator, async_mock_service

MON = date(2026, 11, 16)
BELL = "binary_sensor.klingel"


def bell_rule(**changes: Any) -> dict[str, Any]:
    return {
        "id": "klingel",
        "name": "Klingel",
        "start_triggers": [{"trigger": "state", "entity_id": BELL, "to": "on"}],
        "signals": [
            {"id": "push", "type": "notify", "targets": [PHONE], "message": "{titel}"}
        ],
        **changes,
    }


@pytest.fixture
def pushes(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "notify", PHONE.split(".")[1])


def sent(pushes: list[ServiceCall]) -> list[str]:
    return [
        c.data["message"] for c in pushes if c.data["message"] != "clear_notification"
    ]


async def ring(hass: HomeAssistant) -> None:
    hass.states.async_set(BELL, "off")
    await hass.async_block_till_done()
    hass.states.async_set(BELL, "on")
    await hass.async_block_till_done()
    await hass.async_block_till_done()


async def start(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, **changes: Any
) -> tuple[Any, LaeutwerkManager]:
    freezer.move_to(at(MON, 9))
    hass.states.async_set(BELL, "off")
    entry, manager = await setup_integration(hass)
    await manager.async_create_rule(bell_rule(**changes))
    await hass.async_block_till_done()
    return entry, manager


def test_source_rules() -> None:
    rule = validate_rule(bell_rule(reminders=[{"at": "09:00"}], filter={}))
    assert rule["expire"] == "+12h"
    for bad in (
        bell_rule(sources=["calendar.a"]),
        bell_rule(expire="event_end"),
        bell_rule(expire="event_start"),
    ):
        with pytest.raises(vol.Invalid):
            validate_rule(bad)
    assert (
        validate_rule(
            bell_rule(expire="+30m", start_triggers=[])
            | {"sources": ["calendar.a"], "reminders": [{"at": "09:00"}]}
        )["expire"]
        == "+30m"
    )
    with pytest.raises(vol.Invalid, match="exactly one source"):
        validate_rule(bell_rule(start_triggers=[]))


async def test_trigger_starts_one_reminder(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    _, manager = await start(hass, freezer)
    assert not manager.reminders["klingel"]
    await ring(hass)
    assert sent(pushes) == ["Klingel"]
    assert len(manager.reminders["klingel"]) == 1
    await ring(hass)  # open: nothing new
    assert len(manager.reminders["klingel"]) == 1
    assert len(sent(pushes)) == 1
    await manager.async_acknowledge("klingel")
    freezer.move_to(at(MON, 9, 5))
    await ring(hass)
    assert len(sent(pushes)) == 2
    assert len(manager.reminders["klingel"]) == 2


async def test_trigger_reminder_expires_and_survives_restart(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    entry, manager = await start(hass, freezer)
    await ring(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    freezer.move_to(at(MON, 10))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    manager = entry.runtime_data
    assert len(sent(pushes)) == 1
    assert manager.runners["klingel"].state == "reminded"
    await tick(hass, freezer, at(MON, 21, 1))
    assert manager.runners["klingel"].state == "missed"
    assert len(sent(pushes)) == 1


async def test_unload_and_disable_detach_triggers(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    entry, manager = await start(hass, freezer)
    listener = manager.runners["klingel"]._start_listener
    assert listener is not None and listener.active
    await manager.async_set_enabled("klingel", False)
    assert not listener.active
    await ring(hass)
    assert not sent(pushes)
    await manager.async_set_enabled("klingel", True)
    listener = manager.runners["klingel"]._start_listener
    assert listener is not None and listener.active
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not listener.active
    await ring(hass)
    assert not sent(pushes)


async def test_start_service(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    _, manager = await start(hass, freezer)
    await hass.services.async_call(DOMAIN, "start", {"rule": "klingel"}, blocking=True)
    await hass.services.async_call(DOMAIN, "start", {"rule": "klingel"}, blocking=True)
    assert len(sent(pushes)) == 1
    await manager.async_create_rule(
        {
            "id": "kal",
            "name": "Kal",
            "sources": ["calendar.x"],
            "reminders": [{"at": "09:00"}],
        }
    )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "start", {"rule": "kal"}, blocking=True)


# --------------------------------------------------------------- confirmation


@pytest.fixture(autouse=True)
def phone_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "custom_components.laeutwerk.signals.person_notify_targets",
        lambda hass, person: [PHONE],
    )


async def test_confirm_to_acknowledger_then_clears(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    hass.states.async_set("person.anna", "home", {"friendly_name": "Anna"})
    hass.states.async_set("person.ben", "home", {"friendly_name": "Ben"})
    _, manager = await start(
        hass,
        freezer,
        confirm={"message": "Danke {person}!", "clear_after": 10},
        assignee={"persons": ["person.ben"]},
    )
    await ring(hass)
    pushes.clear()
    await manager.async_acknowledge("klingel", by="Anna", person="person.anna")
    await hass.async_block_till_done()
    assert sent(pushes) == ["Danke Anna!"]
    tag = pushes[-1].data["data"]["tag"]
    assert tag.startswith("laeutwerk_confirm_klingel__")
    await tick(hass, freezer, at(MON, 9, 0) + timedelta(seconds=11))
    assert pushes[-1].data["message"] == "clear_notification"
    assert pushes[-1].data["data"]["tag"] == tag


async def test_confirm_falls_back_to_assignee_or_nobody(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    hass.states.async_set("person.ben", "home", {"friendly_name": "Ben"})
    _, manager = await start(
        hass,
        freezer,
        confirm={"message": "Erledigt, {zustaendig}"},
        assignee={"persons": ["person.ben"]},
    )
    await ring(hass)
    pushes.clear()
    await manager.async_acknowledge("klingel")
    await hass.async_block_till_done()
    assert sent(pushes) == ["Erledigt, Ben"]
    await manager.async_update_rule("klingel", bell_rule(confirm={"message": "x"}))
    await ring(hass)
    pushes.clear()
    await manager.async_acknowledge("klingel")
    await hass.async_block_till_done()
    assert not sent(pushes)


async def test_on_done_entity_variables(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    hass.states.async_set("person.anna", "home", {"friendly_name": "Anna"})
    hass.states.async_set("person.ben", "home", {"friendly_name": "Ben"})
    calls = async_mock_service(hass, "test", "done")
    _, manager = await start(
        hass,
        freezer,
        assignee={"persons": ["person.ben"]},
        on_done=[
            {
                "action": "test.done",
                "data": {"p": "{{ person_entity }}", "z": "{{ zustaendig_entity }}"},
            }
        ],
    )
    await ring(hass)
    await manager.async_acknowledge("klingel", by="Anna", person="person.anna")
    await hass.async_block_till_done()
    assert calls[0].data == {"p": "person.anna", "z": "person.ben"}


# ------------------------------------------------------------ household quiet


async def test_household_quiet_and_own_quiet(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    freezer.move_to(at(MON, 22, 30))
    hass.states.async_set(BELL, "off")
    entry, manager = await setup_integration(hass)
    hass.config_entries.async_update_entry(
        entry, options={"quiet": [{"from": "22:00", "to": "07:00", "mode": "skip"}]}
    )
    silent = {
        "id": "own",
        "type": "notify",
        "targets": [PHONE],
        "message": "own",
        "quiet": [{"from": "01:00", "to": "02:00", "mode": "skip"}],
    }
    base = bell_rule()
    await manager.async_create_rule(bell_rule(signals=[*base["signals"], silent]))
    await hass.async_block_till_done()
    await ring(hass)
    assert sent(pushes) == ["own"]  # own quiet time overrides the household's


async def test_settings_websocket_and_options_flow(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    entry, _ = await setup_integration(hass)
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "laeutwerk/settings"})
    assert (await ws.receive_json())["result"] == {"quiet": None}
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"from": "22:00:00", "to": "07:00:00", "mode": "defer"}
    )
    assert result["type"] == "create_entry"
    assert entry.options["quiet"] == [{"from": "22:00", "to": "07:00", "mode": "defer"}]
    await ws.send_json({"id": 2, "type": "laeutwerk/settings"})
    assert (await ws.receive_json())["result"] == {"quiet": entry.options["quiet"]}
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"from": "22:00:00", "mode": "skip"}
    )
    assert result["errors"] == {"base": "incomplete"}
