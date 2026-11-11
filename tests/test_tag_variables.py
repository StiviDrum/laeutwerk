"""NFC tag ids from variables of the keyword table (e.g. "{nfc}")."""

from __future__ import annotations

from datetime import date
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import issue_registry as ir
import pytest

from custom_components.laeutwerk.compat import vol
from custom_components.laeutwerk.const import DOMAIN
from custom_components.laeutwerk.issues import issue_id
from custom_components.laeutwerk.manager import LaeutwerkManager
from custom_components.laeutwerk.schema import validate_rule

from .common import PHONE, WASTE, FakeCalendars, at, muell_rule, setup_integration, tick
from .ha_testing import async_mock_service

MON = date(2026, 11, 16)
TUE = date(2026, 11, 17)
THU = date(2026, 11, 19)

ROWS = [
    {"match": "Rest", "tonne": "Restmülltonne", "nfc": "restmuelltonne"},
    {"match": "Bio", "tonne": "Biotonne", "nfc": "biomuelltonne"},
    {"match": "Papier", "tonne": "Papiertonne", "nfc": "altpapiertonne"},
    {"match": "Gelb", "tonne": "gelben Sack", "nfc": "gelbetonne"},
]


def tag_rule(acknowledge: list[dict[str, Any]], **changes: Any) -> dict[str, Any]:
    return muell_rule(
        filter={
            "all_day": True,
            "keywords": {
                "columns": ["tonne", {"name": "nfc", "plural": False}],
                "rows": ROWS,
            },
        },
        acknowledge=acknowledge,
        **changes,
    )


VARIABLE = [{"type": "tag", "tag_id": "{nfc}"}]


async def start(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    acknowledge: list[dict[str, Any]],
    when=None,
) -> LaeutwerkManager:
    """Rest + Bio on Tuesday (bundle), Papier on Thursday."""
    freezer.move_to(when or at(MON, 9))
    async_mock_service(hass, "notify", PHONE.split(".")[1])
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Rest", TUE)
    calendars.add_all_day(WASTE, "Bio", TUE)
    calendars.add_all_day(WASTE, "Papier", THU)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(tag_rule(acknowledge))
    await hass.async_block_till_done()
    return manager


async def scan(hass: HomeAssistant, tag_id: str) -> None:
    hass.bus.async_fire("tag_scanned", {"tag_id": tag_id}, context=Context())
    await hass.async_block_till_done()


def states(manager: LaeutwerkManager) -> dict[str, str]:
    return {r.id: r.state for r in manager.reminders["muell"].values()}


async def test_variable_tag_of_the_due_bin(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager = await start(hass, freezer, VARIABLE)
    await tick(hass, freezer, at(MON, 17, 0))
    tuesday = manager.reminders["muell"]["muell__20261117"]
    # The bundle accepts the tag of each of its bins.
    assert manager.runners["muell"].tag_ids(tuesday) == [
        "biomuelltonne",
        "restmuelltonne",
    ]
    assert manager.status("muell")["reminders"][0]["tags"] == [
        "biomuelltonne",
        "restmuelltonne",
    ]

    # Another bin's tag (Papier is due on Thursday, not now) does nothing.
    caplog.set_level("DEBUG", logger="custom_components.laeutwerk")
    await scan(hass, "altpapiertonne")
    await scan(hass, "unbekannt")
    assert states(manager) == {
        "muell__20261117": "reminded",
        "muell__20261119": "planned",
    }
    assert "tag altpapiertonne does not belong to a due reminder" in caplog.text

    # One tag of the bundle finishes the whole bundle.
    await scan(hass, "biomuelltonne")
    assert tuesday.state == "done"
    assert tuesday.acknowledged_via == "tag"
    assert states(manager)["muell__20261119"] == "planned"


async def test_early_before_the_reminder_time(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    # Wednesday 15:00: Papier (Thursday) reminds at 17:00, within the window.
    manager = await start(hass, freezer, VARIABLE, when=at(date(2026, 11, 18), 15))
    await scan(hass, "restmuelltonne")  # Tuesday's bins are over
    assert states(manager)["muell__20261119"] == "planned"
    await scan(hass, "altpapiertonne")
    assert states(manager)["muell__20261119"] == "done"


async def test_too_early_does_nothing(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    # Monday 09:00: Thursday's Papier reminds Wednesday 17:00 – too far ahead.
    manager = await start(hass, freezer, VARIABLE)
    await scan(hass, "altpapiertonne")
    assert states(manager)["muell__20261119"] == "planned"


async def test_fixed_and_variable_mixed(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    acknowledge = [*VARIABLE, {"type": "tag", "tag_id": "haustuer"}]
    manager = await start(hass, freezer, acknowledge)
    await tick(hass, freezer, at(MON, 17, 0))
    # A fixed tag acknowledges like before (whatever is due).
    await scan(hass, "haustuer")
    assert states(manager)["muell__20261117"] == "done"
    await tick(hass, freezer, at(date(2026, 11, 18), 17, 0))
    await scan(hass, "altpapiertonne")
    assert states(manager)["muell__20261119"] == "done"


async def test_fixed_tag_unchanged(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    manager = await start(hass, freezer, [{"type": "tag", "tag_id": "tonne"}])
    await tick(hass, freezer, at(MON, 17, 0))
    await scan(hass, "restmuelltonne")
    assert states(manager)["muell__20261117"] == "reminded"
    await scan(hass, "tonne")
    assert states(manager)["muell__20261117"] == "done"


async def test_listener_after_restart(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    manager = await start(hass, freezer, VARIABLE)
    await tick(hass, freezer, at(MON, 17, 0))
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_unload(entry.entry_id)
    await scan(hass, "restmuelltonne")  # not listening while unloaded
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    manager = entry.runtime_data
    assert states(manager)["muell__20261117"] == "reminded"
    await scan(hass, "restmuelltonne")
    assert states(manager)["muell__20261117"] == "done"
    # Tags are no entities: no repair issue for them.
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id("muell")) is None


def test_validation_of_tag_variables() -> None:
    validate_rule(tag_rule([{"type": "tag", "tag_id": "tonne_{nfc}"}]))
    validate_rule(tag_rule([{"type": "tag", "tag_id": "{tonnen}"}]))  # plural
    validate_rule(tag_rule([{"type": "tag", "tag_id": "{titel}"}]))  # event variable
    with pytest.raises(vol.Invalid, match=r"unknown variable\(s\) \{chip\} in tag_id"):
        validate_rule(tag_rule([{"type": "tag", "tag_id": "{chip}"}]))
    with pytest.raises(vol.Invalid, match=r"\{nfcn\}"):  # plural switched off
        validate_rule(tag_rule([{"type": "tag", "tag_id": "{nfcn}"}]))


async def test_preview_shows_the_resolved_tag(
    hass: HomeAssistant, hass_ws_client
) -> None:
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Gelb", date.today())
    await setup_integration(hass)
    ws = await hass_ws_client(hass)
    await ws.send_json(
        {"id": 1, "type": "laeutwerk/preview", "rule": tag_rule(VARIABLE, id="neu")}
    )
    result = (await ws.receive_json())["result"]
    assert result["events"][0]["tags"] == ["gelbetonne"]
