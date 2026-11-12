"""0.11: send_on, limits only for opportunities, expire never, removed text fields."""

from __future__ import annotations

from collections import Counter

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall
import pytest

from custom_components.laeutwerk.compat import vol
from custom_components.laeutwerk.schema import validate_rule

from .common import PHONE, at, tick
from .ha_testing import async_mock_service
from .test_v010 import BELL, MON, bell_rule, push, ring, sent, start


@pytest.fixture
def pushes(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "notify", PHONE.split(".")[1])


OPP = {"opportunity": [{"trigger": "state", "entity_id": BELL, "to": "on"}]}


def by_id(**extra: object) -> list[dict]:
    return [push(id=name, message=name, **opts) for name, opts in extra.items()]


async def test_send_on_modes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    await start(
        hass,
        freezer,
        at(MON, 9),
        repeat={"every": 90, "max": 5},
        escalation=[{"after": "2h"}, {"after": "4h"}],
        signals=by_id(
            a={},
            f={"send_on": "first"},
            r={"send_on": "repeat"},
            s1={"send_on": "stage", "stage": 1},
            s1r={"send_on": "stage", "stage": 1, "stage_repeat": True},
        ),
    )
    await ring(hass)
    assert Counter(sent(pushes)) == {"a": 1, "f": 1}
    for hour, minute in ((10, 30), (11, 0), (12, 0), (13, 0)):
        await tick(hass, freezer, at(MON, hour, minute))
    assert Counter(sent(pushes)) == {"a": 5, "f": 1, "r": 4, "s1": 1, "s1r": 3}


async def test_send_on_after_snooze(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    manager = await start(
        hass,
        freezer,
        at(MON, 9),
        signals=by_id(f={"send_on": "first"}, r={"send_on": "repeat"}),
    )
    await ring(hass)
    await manager.async_snooze(10)
    await tick(hass, freezer, at(MON, 9, 10))
    assert Counter(sent(pushes)) == {"f": 1, "r": 1}


async def test_never_replaces_open_reminder(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    manager = await start(hass, freezer, at(MON, 9), expire="never")
    await ring(hass)
    freezer.tick(5)
    await ring(hass)
    states = [r.state for r in manager.reminders["klingel"].values()]
    assert sorted(states) == ["missed", "reminded"]


async def test_finite_expire_keeps_single_reminder(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, pushes: list[ServiceCall]
) -> None:
    manager = await start(hass, freezer, at(MON, 9))
    await ring(hass)
    await ring(hass)
    assert len(manager.reminders["klingel"]) == 1


def test_schema_rules() -> None:
    def check(signal: dict, match: str, **rule: object) -> None:
        with pytest.raises(vol.Invalid, match=match):
            validate_rule(bell_rule(signals=[signal], **rule))

    ok = validate_rule(
        bell_rule(
            escalation=[{"after": "1h"}],
            signals=[
                push(message="m", send_on="stage", stage=1, when=OPP),
                push(id="b", message="m", when=OPP, limit={"per_reminder": 1}),
            ],
            expire="never",
        )
    )
    assert ok["expire"] == "never"
    check(push(message="m", send_on="stage"), "needs 'stage'")
    check(push(message="m", send_on="stage", stage=1), "does not exist")
    check(push(message="m", send_on="first", when=OPP), "'all' or 'stage'")
    check(push(message="m", send_on="repeat", when=OPP), "'all' or 'stage'")
    check(push(message="m", limit={"per_reminder": 1}), "limits only apply")
    check(push(message="m", stage=1), "need send_on")
    with pytest.raises(vol.Invalid, match="never"):
        validate_rule(
            {
                "id": "r",
                "name": "R",
                "sources": ["calendar.x"],
                "reminders": [{"at": "-1d 17:00"}],
                "expire": "never",
            }
        )


@pytest.mark.parametrize(
    "field", ["title_plural", "message_repeat", "title_repeat", "every_stage"]
)
def test_removed_fields_rejected(field: str) -> None:
    with pytest.raises(vol.Invalid):
        validate_rule(bell_rule(signals=[push(message="m", **{field: "x"})]))
    with pytest.raises(vol.Invalid):
        validate_rule(bell_rule(headline_plural="x"))


def test_store_migration_0_11() -> None:
    from custom_components.laeutwerk.store import migrate_rule_0_11

    light = {
        "type": "light_signal",
        "entities": ["light.a"],
        "limit": {"per_reminder": 1},
    }
    old = bell_rule(
        headline_plural="x",
        escalation=[{"after": "1h"}],
        signals=[
            push(id="push", message="m", message_plural="p"),
            {"id": "l1", **light},
            {"id": "l2", **light},
            {
                "id": "ansage",
                "type": "announce",
                "players": ["media_player.a"],
                "text": "t",
                "text_plural": "tp",
                "stage": 1,
                "limit": {"per_reminder": 1},
            },
            push(
                id="dryer",
                message="m",
                every_stage=True,
                title_repeat="a",
                message_repeat="b",
            ),
            push(id="stg", message="m", stage=1),
            push(id="opp", message="m", stage=1, when=OPP, limit={"min_interval": 5}),
        ],
    )
    new = migrate_rule_0_11(old)
    signals = {s["id"]: s for s in new["signals"]}
    assert "send_on" not in signals["push"] and "message_plural" not in signals["push"]
    assert signals["l1"]["send_on"] == signals["l2"]["send_on"] == "first"
    assert "limit" not in signals["l1"]
    assert (signals["ansage"]["send_on"], signals["ansage"]["stage_repeat"]) == (
        "stage",
        False,
    )
    assert (
        "send_on" not in signals["dryer"] and "message_repeat" not in signals["dryer"]
    )
    assert signals["stg"]["stage_repeat"] is True
    assert signals["opp"]["send_on"] == "stage" and signals["opp"]["limit"]
    assert "headline_plural" not in new
    validate_rule(new)
