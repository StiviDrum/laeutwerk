"""Entities per rule (SPEC B6)."""

from __future__ import annotations

from datetime import date

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .common import WASTE, FakeCalendars, at, muell_rule, setup_integration, tick
from .ha_testing import async_mock_service

MON = date(2026, 11, 16)
TUE = date(2026, 11, 17)

STATE = "sensor.laeutwerk_muell"
OPEN = "binary_sensor.laeutwerk_muell_offen"
NEXT = "sensor.laeutwerk_muell_naechster_termin"
DONE = "button.laeutwerk_muell_erledigt"
SWITCH = "switch.laeutwerk_muell"


async def test_entities_follow_the_lifecycle(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(at(MON, 9))
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", TUE)
    calendars.add_all_day(WASTE, "Bio", TUE)
    async_mock_service(hass, "notify", "mobile_app_steven")
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await hass.async_block_till_done()

    state = hass.states.get(STATE)
    assert state is not None
    assert state.state == "planned"
    assert state.name == "Müll rausstellen"
    assert state.attributes["rule_id"] == "muell"
    assert state.attributes["event_title"] == "Bio"
    assert state.attributes["bundled_titles"] == ["Bio", "Papier"]
    assert state.attributes["event_start"] == "2026-11-16T23:00:00+00:00"
    assert state.attributes["next_event"] == "2026-11-16T23:00:00+00:00"
    assert state.attributes["variables"]["tonnen"] == "Biotonne und Papiertonne"
    assert state.attributes["acknowledged_by"] is None
    assert hass.states.get(OPEN).state == "off"
    upcoming = hass.states.get(NEXT)
    assert upcoming.state == "2026-11-16T23:00:00+00:00"
    assert upcoming.attributes["title"] == "Bio und Papier"
    assert upcoming.attributes["days_until"] == 1
    assert hass.states.get(SWITCH).state == "on"

    await tick(hass, freezer, at(MON, 17, 0))
    assert hass.states.get(STATE).state == "reminded"
    is_open = hass.states.get(OPEN)
    assert is_open.state == "on"
    assert is_open.attributes["since"] == "2026-11-16T16:00:00+00:00"

    await hass.services.async_call(
        "button", "press", {"entity_id": DONE}, blocking=True
    )
    await hass.async_block_till_done()
    state = hass.states.get(STATE)
    assert state.state == "done"
    assert state.attributes["acknowledged_at"] is not None
    assert hass.states.get(OPEN).state == "off"
    assert manager.reminders["muell"]["muell__20261117"].acknowledged_via == "button"

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": SWITCH}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(SWITCH).state == "off"
    assert hass.states.get(STATE).state == "inactive"
    assert not manager.rules["muell"].enabled


async def test_one_device_per_rule_removed_with_the_rule(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(at(MON, 9))
    FakeCalendars(hass, WASTE)
    entry, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await hass.async_block_till_done()

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert [device.name for device in devices] == ["Müll rausstellen"]
    entities = er.async_entries_for_device(er.async_get(hass), devices[0].id)
    assert sorted(entity.entity_id for entity in entities) == sorted(
        [STATE, OPEN, NEXT, DONE, SWITCH]
    )

    await manager.async_delete_rule("muell")
    await hass.async_block_till_done()
    assert not dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert hass.states.get(STATE) is None
