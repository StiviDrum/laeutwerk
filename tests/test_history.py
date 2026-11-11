"""History of finished reminders, storage migration and diagnostics."""

from __future__ import annotations

from datetime import date
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.laeutwerk.const import DOMAIN, HISTORY_MAX
from custom_components.laeutwerk.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)

from .common import PHONE, WASTE, FakeCalendars, at, muell_rule, setup_integration, tick
from .ha_testing import MockConfigEntry, WebSocketGenerator, async_mock_service

MON = date(2026, 11, 16)


async def test_history(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(at(MON, 9))
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", date(2026, 11, 17))
    calendars.add_all_day(WASTE, "Bio", date(2026, 11, 24))
    async_mock_service(hass, "notify", PHONE.split(".")[1])
    entry, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())

    await tick(hass, freezer, at(MON, 17, 0))
    await manager.async_acknowledge("muell", by="Steven", via="tag")
    await tick(hass, freezer, at(date(2026, 11, 23), 17, 0))
    await tick(hass, freezer, at(date(2026, 11, 24), 12, 0))

    assert [(e["titles"], e["state"]) for e in manager.history["muell"]] == [
        (["Bio"], "missed"),
        (["Papier"], "done"),
    ]
    done = manager.history["muell"][1]
    assert done["acknowledged_by"] == "Steven"
    assert done["acknowledged_via"] == "tag"
    assert done["signals_sent"] == 1
    assert done["day"] == "2026-11-17"

    # The history survives a restart and is limited.
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    manager = entry.runtime_data
    assert len(manager.history["muell"]) == 2
    for n in range(HISTORY_MAX + 5):
        reminder = next(iter(manager.reminders["muell"].values()), None)
        if reminder is None:
            break
        reminder.id = f"x{n}"
        manager._add_history("muell", reminder)
    assert len(manager.history["muell"]) <= HISTORY_MAX

    # Deleting the rule deletes its history.
    await manager.async_delete_rule("muell")
    assert "muell" not in manager.history


async def test_history_websocket(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    FakeCalendars(hass, WASTE)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    manager.history["muell"] = [
        {"reminder_id": "b", "state": "missed"},
        {"reminder_id": "a"},
    ]

    ws = await hass_ws_client(hass)
    await ws.send_json(
        {"id": 1, "type": "laeutwerk/history", "rule_id": "muell", "limit": 1}
    )
    msg = await ws.receive_json()
    assert msg["success"]
    assert msg["result"] == {"history": [{"reminder_id": "b", "state": "missed"}]}
    await ws.send_json({"id": 2, "type": "laeutwerk/history", "rule_id": "nope"})
    assert (await ws.receive_json())["error"]["code"] == "not_found"


async def test_storage_migration_from_1_1(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, hass_storage: dict[str, Any]
) -> None:
    """0.1–0.4 stored version 1.1 without history."""
    freezer.move_to(at(MON, 9))
    FakeCalendars(hass, WASTE)
    hass_storage["laeutwerk"] = {
        "version": 1,
        "minor_version": 1,
        "key": "laeutwerk",
        "data": {"rules": [muell_rule()], "reminders": {}},
    }
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    manager = entry.runtime_data
    assert list(manager.rules) == ["muell"]
    assert manager.history == {}
    assert await hass.config_entries.async_unload(entry.entry_id)
    stored = hass_storage["laeutwerk"]
    assert stored["minor_version"] == 2
    assert stored["data"]["history"] == {}


async def test_diagnostics(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(at(MON, 9))
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", date(2026, 11, 17))
    entry, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["laeutwerk_version"]
    assert result["time_zone"] == "Europe/Berlin"
    assert result["invalid_rules"] == []
    [rule] = result["rules"]
    assert rule["rule"]["id"] == "muell"
    assert rule["status"]["state"] == "planned"
    assert rule["references"]["actions"] == [PHONE]

    [device] = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    single = await async_get_device_diagnostics(hass, entry, device)
    assert single["rule"]["name"] == "Müll rausstellen"
    assert single["status"]["reminders"][0]["titles"] == ["Papier"]
