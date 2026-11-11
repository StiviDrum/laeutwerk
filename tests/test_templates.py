"""Templates (built in and own) and YAML export / import."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError, Unauthorized
import pytest

from custom_components.laeutwerk.compat import vol
from custom_components.laeutwerk.manager import LaeutwerkManager
from custom_components.laeutwerk.schema import validate_rule
from custom_components.laeutwerk.templates import (
    builtin_templates,
    export_yaml,
    parse_rules_yaml,
)

from .common import (
    KULT,
    WASTE,
    FakeCalendars,
    kult61_rule,
    muell_rule,
    setup_integration,
)
from .ha_testing import WebSocketGenerator


@pytest.fixture
async def manager(hass: HomeAssistant) -> LaeutwerkManager:
    FakeCalendars(hass, WASTE, KULT)
    _, manager = await setup_integration(hass)
    return manager


@pytest.mark.parametrize("language", ["de", "en"])
def test_builtin_templates_are_valid_rules(language: str) -> None:
    templates = builtin_templates(language)
    assert [t["id"] for t in templates] == [
        "builtin_muell",
        "builtin_geburtstag",
        "builtin_wartung",
        "builtin_medikamente",
    ]
    for template in templates:
        rule = {**template["rule"], "id": "x"}
        if not rule.get("interval"):
            rule["sources"] = ["calendar.x"]
        validate_rule(rule)
    assert builtin_templates("de")[0]["name"] == "Müll rausstellen"
    assert builtin_templates("en-GB")[0]["name"] == "Put out the bins"


def test_yaml_round_trip() -> None:
    rule = validate_rule(muell_rule())
    text = export_yaml([{**rule, "status": {"state": "planned"}}])
    assert "status" not in text
    assert "Müll rausstellen" in text
    assert parse_rules_yaml(text) == [{k: v for k, v in rule.items() if v is not None}]
    assert len(parse_rules_yaml(export_yaml([rule, rule]))) == 2
    for broken in ("name: [unclosed", "- 1\n- 2", "just text"):
        with pytest.raises(vol.Invalid):
            parse_rules_yaml(broken)


async def test_import_and_export(
    hass: HomeAssistant, manager: LaeutwerkManager
) -> None:
    await manager.async_create_rule(muell_rule())
    text = manager.export_rules(["muell"])

    # Importing the same rule again gives it a new id.
    [copy] = await manager.async_import_rules(text)
    assert copy.id == "muell_rausstellen"
    assert copy.name == "Müll rausstellen"

    # A list imports all rules – or none, if one of them is invalid.
    broken = export_yaml([kult61_rule(), {**muell_rule(id="neu"), "reminders": []}])
    with pytest.raises(vol.Invalid):
        await manager.async_import_rules(broken)
    assert "kult61" not in manager.rules
    both = export_yaml([kult61_rule(), muell_rule(id="neu")])
    assert [r.id for r in await manager.async_import_rules(both)] == ["kult61", "neu"]

    # Services: export all rules, import as admin.
    result = await hass.services.async_call(
        "laeutwerk", "export_rules", {}, blocking=True, return_response=True
    )
    assert len(parse_rules_yaml(result["yaml"])) == 4
    result = await hass.services.async_call(
        "laeutwerk",
        "import_rules",
        {"yaml": manager.export_rules(["kult61"])},
        blocking=True,
        return_response=True,
    )
    assert result == {"rules": ["kult61_dienst"]}
    with pytest.raises(ServiceValidationError, match="invalid YAML"):
        await hass.services.async_call(
            "laeutwerk", "import_rules", {"yaml": "a: [b"}, blocking=True
        )


async def test_own_templates(hass: HomeAssistant, manager: LaeutwerkManager) -> None:
    await manager.async_create_rule(muell_rule())
    template = manager.save_template("Meine Tonnen", manager.rules["muell"].to_dict())
    assert template["id"] == "user_meine_tonnen"
    assert "sources" not in template["rule"]
    assert "id" not in template["rule"]
    listed = manager.list_templates()
    assert [t["builtin"] for t in listed] == [True] * 4 + [False]
    assert listed[-1]["rule"]["filter"]["keywords"]["columns"] == [
        "tonne",
        "farbe",
        "artikel",
    ]
    # A template without sources can become a rule once a calendar is chosen.
    await manager.async_create_rule({**template["rule"], "sources": [WASTE]})
    with pytest.raises(vol.Invalid):
        manager.save_template("kaputt", {"name": "x", "reminders": []})
    manager.delete_template("user_meine_tonnen")
    assert len(manager.list_templates()) == 4


async def test_websocket(
    hass: HomeAssistant,
    manager: LaeutwerkManager,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_access_token: str,
) -> None:
    await manager.async_create_rule(muell_rule())
    ws = await hass_ws_client(hass)
    n = 0

    async def send(type_: str, **data: Any) -> dict[str, Any]:
        nonlocal n
        n += 1
        await ws.send_json({"id": n, "type": f"laeutwerk/{type_}", **data})
        return await ws.receive_json()

    listed = await send("templates/list")
    assert len(listed["result"]["templates"]) == 4
    saved = await send("templates/save", name="Tonnen", rule_id="muell")
    assert saved["result"]["id"] == "user_tonnen"
    unsaved = await send("templates/save", name="Neu", rule=kult61_rule())
    assert unsaved["success"]
    assert len((await send("templates/list"))["result"]["templates"]) == 6
    assert (await send("templates/delete", template_id="user_neu"))["success"]
    assert (await send("templates/delete", template_id="nope"))["error"]["code"] == (
        "home_assistant_error"
    )

    exported = await send("rules/export")
    assert "Müll rausstellen" in exported["result"]["yaml"]
    imported = await send("rules/import", yaml=exported["result"]["yaml"])
    assert [r["id"] for r in imported["result"]["rules"]] == ["muell_rausstellen"]
    bad = await send("rules/import", yaml="name: x")
    assert bad["error"]["code"] == "invalid_format"

    # Read-only users may list and export, but not save, delete or import.
    ro = await hass_ws_client(hass, hass_read_only_access_token)
    await ro.send_json({"id": 1, "type": "laeutwerk/rules/export"})
    assert (await ro.receive_json())["success"]
    for i, (type_, data) in enumerate(
        (
            ("templates/save", {"name": "x", "rule_id": "muell"}),
            ("templates/delete", {"template_id": "user_tonnen"}),
            ("rules/import", {"yaml": exported["result"]["yaml"]}),
        ),
        start=2,
    ):
        await ro.send_json({"id": i, "type": f"laeutwerk/{type_}", **data})
        assert (await ro.receive_json())["error"]["code"] == "unauthorized"


async def test_import_requires_admin(
    hass: HomeAssistant, manager: LaeutwerkManager, hass_read_only_user
) -> None:
    from homeassistant.core import Context

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            "laeutwerk",
            "import_rules",
            {"yaml": export_yaml([muell_rule()])},
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )
