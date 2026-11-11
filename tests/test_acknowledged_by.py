"""Who acknowledged: person, else the user's name; nobody for automations."""

from __future__ import annotations

from datetime import date
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import Context, HomeAssistant
import pytest

from custom_components.laeutwerk.manager import LaeutwerkManager

from .common import PHONE, WASTE, FakeCalendars, at, muell_rule, setup_integration, tick
from .ha_testing import async_mock_service

MON = date(2026, 11, 16)
TUE = date(2026, 11, 17)
REMINDER = "muell__20261117"
BUTTON = "button.laeutwerk_muell_erledigt"


@pytest.fixture
async def manager(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> LaeutwerkManager:
    """Papier on Tuesday, reminding since Monday 17:00."""
    freezer.move_to(at(MON, 9))
    async_mock_service(hass, "notify", PHONE.split(".")[1])
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", TUE)
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(muell_rule())
    await tick(hass, freezer, at(MON, 17, 0))
    return manager


def done(manager: LaeutwerkManager) -> tuple[Any, ...]:
    reminder = manager.reminders["muell"][REMINDER]
    return (
        reminder.state,
        reminder.acknowledged_by,
        reminder.acknowledged_via,
        reminder.acknowledged_person,
    )


async def press(hass: HomeAssistant, context: Context) -> None:
    await hass.services.async_call(
        "button", "press", {"entity_id": BUTTON}, blocking=True, context=context
    )
    await hass.async_block_till_done()


async def test_user_with_person(
    hass: HomeAssistant, manager: LaeutwerkManager, hass_admin_user
) -> None:
    hass.states.async_set(
        "person.steven",
        "home",
        {"friendly_name": "Steven", "user_id": hass_admin_user.id},
    )
    await press(hass, Context(user_id=hass_admin_user.id))
    assert done(manager) == ("done", "Steven", "button", "person.steven")
    assert manager.history["muell"][0]["acknowledged_person"] == "person.steven"


async def test_user_without_person_falls_back_to_user_name(
    hass: HomeAssistant, manager: LaeutwerkManager, hass_admin_user
) -> None:
    await press(hass, Context(user_id=hass_admin_user.id))
    assert done(manager) == ("done", hass_admin_user.name, "button", None)
    assert hass_admin_user.name  # "Mock User"


async def test_system_user_automation_and_no_context(
    hass: HomeAssistant, manager: LaeutwerkManager, hass_admin_user
) -> None:
    system = await hass.auth.async_create_system_user(
        "Läutwerk Test", group_ids=["system-admin"]
    )
    await press(hass, Context(user_id=system.id))
    assert done(manager)[1] is None
    # Next week's reminder: an automation pressing the button (parent context).
    manager.reminders["muell"][REMINDER].state = "reminded"
    await press(hass, Context(user_id=hass_admin_user.id, parent_id="01AUTOMATION"))
    assert done(manager)[1:] == (None, "button", None)
    # The acknowledge action from an automation (no user): nobody.
    manager.reminders["muell"][REMINDER].state = "reminded"
    await hass.services.async_call(
        "laeutwerk", "acknowledge", {"rule": "muell"}, blocking=True
    )
    assert done(manager)[1:] == (None, "service", None)


async def test_service_with_user_and_explicit_person(
    hass: HomeAssistant, manager: LaeutwerkManager, hass_admin_user
) -> None:
    hass.states.async_set("person.anna", "home", {"friendly_name": "Anna"})
    await hass.services.async_call(
        "laeutwerk",
        "acknowledge",
        {"rule": "muell"},
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )
    assert done(manager) == ("done", hass_admin_user.name, "service", None)
    # An explicit person (name or entity id) wins and is linked to the entity.
    for given in ("Anna", "person.anna"):
        manager.reminders["muell"][REMINDER].state = "reminded"
        await hass.services.async_call(
            "laeutwerk",
            "acknowledge",
            {"rule": "muell", "person": given},
            blocking=True,
        )
        assert done(manager)[1:] == ("Anna", "service", "person.anna")


async def test_push_action_and_tag_unchanged(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_admin_user,
    hass_read_only_user,
) -> None:
    hass.states.async_set(
        "person.steven",
        "home",
        {"friendly_name": "Steven", "user_id": hass_admin_user.id},
    )
    freezer.move_to(at(MON, 9))
    async_mock_service(hass, "notify", PHONE.split(".")[1])
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", TUE)
    calendars.add_all_day(WASTE, "Bio", date(2026, 11, 24))
    _, manager = await setup_integration(hass)
    await manager.async_create_rule(
        muell_rule(
            acknowledge=[{"type": "notify_action"}, {"type": "tag", "tag_id": "tonne"}]
        )
    )
    await tick(hass, freezer, at(MON, 17, 0))
    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": f"LAEUTWERK_ACK__{REMINDER}"},
        context=Context(user_id=hass_admin_user.id),
    )
    await hass.async_block_till_done()
    assert done(manager) == ("done", "Steven", "notify_action", "person.steven")

    await tick(hass, freezer, at(date(2026, 11, 23), 17, 0))
    hass.bus.async_fire(
        "tag_scanned", {"tag_id": "tonne"}, context=Context(user_id=hass_admin_user.id)
    )
    await hass.async_block_till_done()
    bio = manager.reminders["muell"]["muell__20261124"]
    assert (bio.acknowledged_by, bio.acknowledged_via, bio.acknowledged_person) == (
        "Steven",
        "tag",
        "person.steven",
    )
    # A push from a user without person: the user's name.
    manager.reminders["muell"]["muell__20261124"].state = "reminded"
    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": "LAEUTWERK_ACK__muell__20261124"},
        context=Context(user_id=hass_read_only_user.id),
    )
    await hass.async_block_till_done()
    assert (bio.acknowledged_by, bio.acknowledged_person) == (
        hass_read_only_user.name,
        None,
    )


async def test_rotation_after_last_ignores_user_names(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set("person.steven", "home", {"friendly_name": "Steven"})
    hass.states.async_set("person.anna", "home", {"friendly_name": "Anna"})
    freezer.move_to(at(MON, 9))
    calendars = FakeCalendars(hass, WASTE)
    calendars.add_all_day(WASTE, "Papier", TUE)
    _, manager = await setup_integration(hass)
    manager.history["muell"] = [
        # Newest: a user without person – even one named like a person.
        {"state": "done", "acknowledged_by": "Anna", "acknowledged_person": None},
        {"state": "missed"},
        {
            "state": "done",
            "acknowledged_by": "Steven",
            "acknowledged_person": "person.steven",
        },
    ]
    rule = muell_rule(
        assignee={"persons": ["person.steven", "person.anna"], "rotation": "after_last"}
    )
    await manager.async_create_rule(rule)
    await hass.async_block_till_done()
    assert manager.reminders["muell"][REMINDER].assignee == "person.anna"

    # Entries from before 0.6.2 (no person entity) are matched by name.
    await manager.async_delete_rule("muell")
    manager.history["muell"] = [{"state": "done", "acknowledged_by": "Anna"}]
    await manager.async_create_rule(rule)
    await hass.async_block_till_done()
    assert manager.reminders["muell"][REMINDER].assignee == "person.steven"
