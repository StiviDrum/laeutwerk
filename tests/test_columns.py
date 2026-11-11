"""Keyword columns with switchable plural (0.6.2)."""

from __future__ import annotations

from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
import pytest

from custom_components.laeutwerk.compat import vol
from custom_components.laeutwerk.matching import build_variables, parse_event
from custom_components.laeutwerk.model import Rule
from custom_components.laeutwerk.schema import validate_rule
from custom_components.laeutwerk.templates import parse_rules_yaml

from .common import KULT, WASTE, FakeCalendars, muell_rule, setup_integration

TZ = ZoneInfo("Europe/Berlin")
TUE = date(2026, 11, 17)

COLUMNS = [
    "tonne",  # short form: plural {tonnen}
    {"name": "farbe", "plural": "farben"},  # explicit default name -> short form
    {"name": "artikel", "plural": False},  # no plural variable
    {"name": "ort", "plural": True},  # reserved name check still applies
]


def rule_with(columns: list[Any], rows: list[dict[str, str]] | None = None) -> dict:
    return muell_rule(
        filter={
            "all_day": True,
            "keywords": {
                "columns": columns,
                "rows": rows
                or [
                    {
                        "match": "Papier",
                        "tonne": "Papiertonne",
                        "farbe": "blau",
                        "artikel": "die",
                    },
                    {
                        "match": "Bio",
                        "tonne": "Biotonne",
                        "farbe": "grün",
                        "artikel": "die",
                    },
                    {
                        "match": "Gelb",
                        "tonne": "gelben Sack",
                        "farbe": "gelb",
                        "artikel": "den",
                    },
                ],
            },
        }
    )


def variables(data: dict, *titles: str) -> dict[str, str]:
    rule = Rule.from_dict(validate_rule(data))
    events = [
        parse_event(
            WASTE,
            {"start": TUE.isoformat(), "end": "2026-11-18", "summary": title},
            TZ,
        )
        for title in titles
    ]
    return build_variables(rule, events, today=date(2026, 11, 16), tz=TZ, language="de")


def test_both_forms_and_short_storage() -> None:
    with pytest.raises(vol.Invalid, match="reserved"):
        validate_rule(rule_with(COLUMNS))
    columns = COLUMNS[:3]
    stored = validate_rule(rule_with(columns))["filter"]["keywords"]["columns"]
    # Stored in the short form while the plural is the default.
    assert stored == ["tonne", "farbe", {"name": "artikel", "plural": False}]
    rule = Rule.from_dict(validate_rule(rule_with(columns)))
    assert rule.filter.columns == ["tonne", "farbe", "artikel"]
    assert rule.to_dict()["filter"]["keywords"]["columns"] == stored


def test_variables_without_plural() -> None:
    columns = ["tonne", "farbe", {"name": "artikel", "plural": False}]
    one = variables(rule_with(columns), "Papier")
    assert one["artikel"] == "die"
    assert "artikeln" not in one
    assert one["tonnen"] == "Papiertonne"

    # Bundle: the unique values, joined – one value if they are all the same.
    same = variables(rule_with(columns), "Papier", "Bio")
    assert same["artikel"] == "die"
    mixed = variables(rule_with(columns), "Papier", "Gelb")
    assert mixed["artikel"] == "die und den"
    assert mixed["tonne"] == "Papiertonne"  # with plural: the first value
    assert mixed["tonnen"] == "Papiertonne und gelben Sack"


def test_own_plural_name() -> None:
    columns = [{"name": "tonne", "plural": "tonnen_liste"}]
    rows = [
        {"match": "Papier", "tonne": "Papiertonne"},
        {"match": "Bio", "tonne": "Biotonne"},
    ]
    values = variables(rule_with(columns, rows), "Papier", "Bio")
    assert values["tonnen_liste"] == "Papiertonne und Biotonne"
    assert "tonnen" not in values
    stored = validate_rule(rule_with(columns, rows))["filter"]["keywords"]["columns"]
    assert stored == [{"name": "tonne", "plural": "tonnen_liste"}]


def test_clash_check_only_for_active_plurals() -> None:
    rows = [{"match": "x", "tonne": "a", "tonnen": "b"}]
    with pytest.raises(vol.Invalid, match="plural variable 'tonnen' clashes"):
        validate_rule(rule_with(["tonne", "tonnen"], rows))
    # Plural off: "tonne" and "tonnen" can both be columns.
    validate_rule(rule_with([{"name": "tonne", "plural": False}, "tonnen"], rows))
    # An own plural name must not clash either.
    with pytest.raises(vol.Invalid, match="plural variable 'wann' clashes"):
        validate_rule(
            rule_with([{"name": "tonne", "plural": "wann"}], [{"match": "x"}])
        )
    with pytest.raises(vol.Invalid, match="single word"):
        validate_rule(
            rule_with([{"name": "zwei wörter", "plural": False}], [{"match": "x"}])
        )
    with pytest.raises(vol.Invalid):
        validate_rule(rule_with([{"plural": False}], [{"match": "x"}]))


async def test_round_trip_services_and_yaml(hass: HomeAssistant) -> None:
    FakeCalendars(hass, WASTE, KULT)
    _, manager = await setup_integration(hass)
    columns = [
        "tonne",
        {"name": "artikel", "plural": False},
        {"name": "farbe", "plural": "farbtoene"},
    ]
    expected = [
        "tonne",
        {"name": "artikel", "plural": False},
        {"name": "farbe", "plural": "farbtoene"},
    ]
    await hass.services.async_call(
        "laeutwerk", "create_rule", {"config": rule_with(columns)}, blocking=True
    )
    rules = await hass.services.async_call(
        "laeutwerk", "get_rules", {"rule": "muell"}, blocking=True, return_response=True
    )
    assert rules["rules"][0]["filter"]["keywords"]["columns"] == expected

    exported = await hass.services.async_call(
        "laeutwerk",
        "export_rules",
        {"rule": "muell"},
        blocking=True,
        return_response=True,
    )
    assert (
        parse_rules_yaml(exported["yaml"])[0]["filter"]["keywords"]["columns"]
        == expected
    )
    imported = await hass.services.async_call(
        "laeutwerk",
        "import_rules",
        {"yaml": exported["yaml"]},
        blocking=True,
        return_response=True,
    )
    copy = manager.rules[imported["rules"][0]]
    assert copy.to_dict()["filter"]["keywords"]["columns"] == expected
    assert copy.filter.plural("artikel") is None
    assert copy.filter.plural("farbe") == "farbtoene"

    # Own templates keep the columns as well.
    template = manager.save_template("Tonnen", manager.rules["muell"].to_dict())
    assert template["rule"]["filter"]["keywords"]["columns"] == expected
