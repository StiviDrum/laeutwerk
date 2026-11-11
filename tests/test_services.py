"""Services: acknowledge, trigger, read and edit rules."""

from __future__ import annotations

from datetime import date
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError, Unauthorized
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
from .ha_testing import async_mock_service

MON = date(2026, 11, 16)
TUE = date(2026, 11, 17)


async def call(
    hass: HomeAssistant, service: str, response: bool = False, **data: Any
) -> Any:
    result = await hass.services.async_call(
        "laeutwerk", service, data, blocking=True, return_response=response
    )
    await hass.async_block_till_done()
    return result


@pytest.fixture
async def manager(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> LaeutwerkManager:
    freezer.move_to(at(MON, 9))
    calendars = FakeCalendars(hass, WASTE, KULT)
    calendars.add_all_day(WASTE, "Papier", TUE)
    calendars.add_timed(KULT, "Dienst: Theke", at(TUE, 19))
    async_mock_service(hass, "notify", "mobile_app_steven")
    _, manager = await setup_integration(hass)
    return manager


async def test_create_get_update_delete(
    hass: HomeAssistant, manager: LaeutwerkManager
) -> None:
    result = await call(hass, "create_rule", response=True, config=muell_rule())
    assert result == {"rule": "muell"}

    # Without an id the name is used; an existing id is refused.
    rule = kult61_rule()
    del rule["id"]
    assert await call(hass, "create_rule", response=True, config=rule) == {
        "rule": "kult61_dienst"
    }
    with pytest.raises(ServiceValidationError, match="already exists"):
        await call(hass, "create_rule", config=muell_rule())

    rules = (await call(hass, "get_rules", response=True))["rules"]
    assert [r["id"] for r in rules] == ["muell", "kult61_dienst"]
    muell = rules[0]
    assert muell["reminders"] == [{"at": "-1d 17:00"}]
    assert muell["filter"]["keywords"]["rows"][0] == {
        "match": "Papier",
        "tonne": "Papiertonne",
        "farbe": "blau",
        "artikel": "die",
    }
    status = muell["status"]
    assert status["state"] == "planned"
    assert status["current"] == "muell__20261117"
    assert status["next_event"]["titles"] == ["Papier"]
    assert status["next_event"]["days_until"] == 1
    reminder = status["reminders"][0]
    assert reminder["next_reminder_at"] == "2026-11-16T16:00:00+00:00"
    assert reminder["expires_at"] == "2026-11-17T11:00:00+00:00"
    assert reminder["variables"]["wann"] == "morgen"
    # What get_rules returns can be passed to create_rule again.
    copy = {k: v for k, v in muell.items() if k != "status"} | {"id": "muell_b"}
    assert await call(hass, "create_rule", response=True, config=copy) == {
        "rule": "muell_b"
    }

    only_one = await call(hass, "get_rules", response=True, rule="kult61_dienst")
    assert [r["id"] for r in only_one["rules"]] == ["kult61_dienst"]

    # update_rule replaces the given top-level keys only.
    await call(
        hass, "update_rule", rule="muell", config={"reminders": [{"at": "-1d 18:30"}]}
    )
    assert manager.rules["muell"].reminders == ["-1d 18:30"]
    assert manager.rules["muell"].name == "Müll rausstellen"
    assert len(manager.rules["muell"].signals) == 1
    with pytest.raises(ServiceValidationError, match="invalid time"):
        await call(
            hass, "update_rule", rule="muell", config={"reminders": [{"at": "abends"}]}
        )
    with pytest.raises(ServiceValidationError):
        await call(hass, "update_rule", rule="nope", config={"name": "x"})

    await call(hass, "delete_rule", rule="muell")
    assert "muell" not in manager.rules
    with pytest.raises(ServiceValidationError):
        await call(hass, "delete_rule", rule="muell")


async def test_duplicate_enable_disable(
    hass: HomeAssistant, manager: LaeutwerkManager
) -> None:
    await call(hass, "create_rule", config=muell_rule())
    result = await call(hass, "duplicate_rule", response=True, rule="muell")
    assert result == {"rule": "muell_rausstellen_kopie"}
    copy = manager.rules["muell_rausstellen_kopie"]
    assert copy.name == "Müll rausstellen (Kopie)"
    assert not copy.enabled

    await call(hass, "enable")
    assert all(rule.enabled for rule in manager.rules.values())
    await call(hass, "disable", rule=["muell"])
    assert not manager.rules["muell"].enabled
    assert manager.rules["muell_rausstellen_kopie"].enabled
    await call(hass, "enable", rule="muell")
    assert manager.rules["muell"].enabled
    with pytest.raises(ServiceValidationError):
        await call(hass, "enable", rule="nope")


async def test_acknowledge_and_trigger(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, manager: LaeutwerkManager
) -> None:
    await call(hass, "create_rule", config=muell_rule())
    await call(hass, "create_rule", config=kult61_rule())

    # Without a rule only reminders that are reminding are acknowledged.
    assert await call(hass, "acknowledge", response=True) == {"acknowledged": []}

    # trigger reminds now, regardless of the reminder time.
    await call(hass, "trigger", rule="kult61")
    assert manager.status("kult61")["state"] == "reminded"
    assert manager.status("muell")["state"] == "planned"

    await tick(hass, freezer, at(MON, 17, 0))
    result = await call(hass, "acknowledge", response=True, person="Steven")
    assert sorted(result["acknowledged"]) == ["kult61__20261117", "muell__20261117"]
    reminder = manager.reminders["muell"]["muell__20261117"]
    assert reminder.acknowledged_by == "Steven"
    assert reminder.acknowledged_via == "service"

    with pytest.raises(ServiceValidationError):
        await call(hass, "acknowledge", rule="nope")
    with pytest.raises(ServiceValidationError):
        await call(hass, "trigger", rule="muell")  # nothing left to remind of
    await call(hass, "disable", rule="muell")
    with pytest.raises(ServiceValidationError):
        await call(hass, "trigger", rule="muell")


async def test_acknowledge_single_reminder(
    hass: HomeAssistant, manager: LaeutwerkManager
) -> None:
    await call(hass, "create_rule", config=muell_rule())
    result = await call(
        hass, "acknowledge", response=True, reminder_id="muell__20261117"
    )
    assert result == {"acknowledged": ["muell__20261117"]}
    assert manager.status("muell")["state"] == "done"


async def test_editing_requires_admin(
    hass: HomeAssistant, manager: LaeutwerkManager, hass_read_only_user, hass_admin_user
) -> None:
    user = Context(user_id=hass_read_only_user.id)
    admin = Context(user_id=hass_admin_user.id)

    async def as_user(context: Context, service: str, **data: Any) -> None:
        await hass.services.async_call(
            "laeutwerk", service, data, blocking=True, context=context
        )

    with pytest.raises(Unauthorized):
        await as_user(user, "create_rule", config=muell_rule())
    await as_user(admin, "create_rule", config=muell_rule())
    for service, data in (
        ("update_rule", {"rule": "muell", "config": {"name": "x"}}),
        ("duplicate_rule", {"rule": "muell"}),
        ("delete_rule", {"rule": "muell"}),
    ):
        with pytest.raises(Unauthorized):
            await as_user(user, service, **data)
    # Acknowledging is allowed for everyone.
    await as_user(user, "acknowledge", rule="muell")
    assert manager.rules["muell"].name == "Müll rausstellen"
