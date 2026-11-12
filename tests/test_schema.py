"""Rule validation and model round trip."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.laeutwerk.compat import vol
from custom_components.laeutwerk.model import Reminder, Rule
from custom_components.laeutwerk.schema import make_rule_id, validate_rule

from .common import kult61_rule, muell_rule


def test_reference_rules_round_trip() -> None:
    for data in (muell_rule(), kult61_rule()):
        rule = Rule.from_dict(validate_rule(data))
        stored = rule.to_dict()
        assert Rule.from_dict(validate_rule(stored)).to_dict() == stored
    rule = Rule.from_dict(validate_rule(kult61_rule()))
    assert rule.reminders == ["-1d 20:00", "-2h"]
    assert rule.filter.rows[0].mode == "startswith"
    assert rule.bundle is True
    assert rule.signals[0].config["targets"] == ["notify.mobile_app_steven"]


def test_defaults_and_signal_ids() -> None:
    rule = validate_rule(
        {
            "id": "geburtstage",
            "name": " Geburtstage ",
            "sources": "calendar.geburtstage",
            "reminders": [{"at": "-7d 09:00"}, {"at": "09:00"}],
            "signals": [
                {"type": "notify", "targets": "notify.a", "message": "x"},
                {"type": "notify", "targets": ["notify.b"], "message": "y"},
                {
                    "id": "notify_2",
                    "type": "notify",
                    "targets": ["notify.c"],
                    "message": "z",
                },
            ],
        }
    )
    assert rule["name"] == "Geburtstage"
    assert rule["sources"] == ["calendar.geburtstage"]
    assert rule["expire"] == "event_end"
    assert rule["filter"] == {"all_day": False, "keywords": {"columns": [], "rows": []}}
    assert [s["id"] for s in rule["signals"]] == ["notify", "notify_3", "notify_2"]
    assert rule["signals"][0]["when"] == "now"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"name": "  "}, "must not be empty"),
        ({"sources": []}, "exactly one source"),
        ({"sources": ["light.lampe"]}, "cannot be a source"),
        ({"sources": ["calendar.a", "calendar.a"]}, "unique|duplicate"),
        ({"reminders": []}, "at least one reminder time"),
        ({"reminders": [{"at": "morgen früh"}]}, "invalid time"),
        ({"reminders": [{"at": "event_end"}]}, "only allowed for 'expire'"),
        ({"reminders": [{"at": "09:00"}, {"at": "09:00"}]}, "unique"),
        ({"expire": "irgendwann"}, "invalid time"),
        ({"repeat": "hourly"}, "repeat"),
        ({"signals": [{"type": "fax", "message": "x"}]}, "unknown signal type"),
        (
            {"signals": [{"type": "notify", "targets": ["light.x"], "message": "x"}]},
            "not a notify action",
        ),
        (
            {"signals": [{"type": "notify", "targets": ["notify.x"]}]},
            "message",
        ),
        (
            {
                "signals": [
                    {
                        "id": "a",
                        "type": "notify",
                        "targets": ["notify.x"],
                        "message": "x",
                    },
                    {
                        "id": "a",
                        "type": "notify",
                        "targets": ["notify.x"],
                        "message": "x",
                    },
                ]
            },
            "signal ids must be unique",
        ),
        ({"unknown_key": 1}, "unknown_key"),
    ],
)
def test_invalid_rules(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(vol.Invalid, match=message):
        validate_rule(muell_rule(**changes))


@pytest.mark.parametrize(
    ("keywords", "message"),
    [
        ({"columns": ["a", "a"]}, "unique"),
        ({"columns": ["wann"]}, "reserved"),
        ({"columns": ["match"]}, "reserved"),
        ({"columns": ["zwei wörter"]}, "single word"),
        ({"columns": ["orte", "ort"]}, "reserved"),
        ({"columns": ["tonne", "tonnen"]}, "plural variable"),
        ({"columns": ["a"], "rows": [{"match": "x", "b": "1"}]}, "unknown column"),
        ({"rows": [{"match": " "}]}, "row 1: 'match'"),
        ({"rows": [{"match": "x", "mode": "fuzzy"}]}, "mode must be"),
        ({"rows": [{"match": "(", "mode": "regex"}]}, "invalid regular expression"),
    ],
)
def test_invalid_keyword_tables(keywords: dict[str, Any], message: str) -> None:
    with pytest.raises(vol.Invalid, match=message):
        validate_rule(muell_rule(filter={"keywords": keywords}))


def test_keyword_rows_are_normalised() -> None:
    rule = validate_rule(
        muell_rule(
            filter={
                "keywords": {
                    "columns": ["Tonne", "größe"],
                    "rows": [{"match": " Papier ", "TONNE": "Papiertonne"}],
                }
            }
        )
    )
    assert rule["filter"]["keywords"] == {
        "columns": ["tonne", "größe"],
        "rows": [{"match": "Papier", "tonne": "Papiertonne", "größe": ""}],
    }


def test_make_rule_id() -> None:
    assert make_rule_id("Müll rausstellen", set()) == "muell_rausstellen"
    assert make_rule_id("Müll rausstellen", {"muell_rausstellen"}) == (
        "muell_rausstellen_2"
    )
    assert make_rule_id("!!!", set()) == "rule"


def test_reminder_round_trip() -> None:
    data = {
        "id": "muell__20261117",
        "rule_id": "muell",
        "day": "2026-11-17",
        "start": "2026-11-16T23:00:00+00:00",
        "end": "2026-11-17T23:00:00+00:00",
        "events": [
            {
                "calendar": "calendar.abfallkalender",
                "summary": "Papier",
                "start": "2026-11-16T23:00:00+00:00",
                "end": "2026-11-17T23:00:00+00:00",
                "all_day": True,
                "day": "2026-11-17",
                "description": "",
                "location": "",
            }
        ],
        "state": "done",
        "fired": ["-1d 17:00"],
        "reminded_at": "2026-11-16T16:00:00+00:00",
        "finished_at": "2026-11-16T19:41:00+00:00",
        "acknowledged_by": "Steven",
        "acknowledged_via": "button",
        "acknowledged_person": "person.steven",
        "signals_sent": {"push": 1},
        "signal_last": {"push": "2026-11-16T16:00:00+00:00"},
        "deferred": {"ansage": "2026-11-17T07:00:00+00:00"},
        "snoozed_until": None,
        "repeats": 2,
        "last_reminded": "2026-11-16T18:00:00+00:00",
        "stage": 1,
        "nr": 0,
        "assignee": "person.steven",
        "substitute_for": None,
        "trigger_person": "",
    }
    assert Reminder.from_dict(data).to_dict() == data
