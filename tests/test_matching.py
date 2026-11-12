"""Filter, keyword table, bundling and variables (pure logic)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from custom_components.laeutwerk.matching import (
    build_occurrences,
    build_variables,
    describe_day,
    join_words,
    match_event,
    parse_event,
    render,
    rest_of_title,
    template_variables,
)
from custom_components.laeutwerk.model import CalendarEvent, Rule
from custom_components.laeutwerk.schema import validate_rule

from .common import KULT, WASTE, kult61_rule, muell_rule

TZ = ZoneInfo("Europe/Berlin")
TUE = date(2026, 11, 17)


def rule_of(data: dict[str, Any]) -> Rule:
    return Rule.from_dict(validate_rule(data))


def all_day(summary: str, day: date = TUE, calendar: str = WASTE) -> CalendarEvent:
    return parse_event(
        calendar,
        {
            "start": day.isoformat(),
            "end": f"{day.replace(day=day.day + 1)}",
            "summary": summary,
        },
        TZ,
    )


def timed(
    summary: str, start: str, calendar: str = KULT, **extra: str
) -> CalendarEvent:
    end = datetime.fromisoformat(start).replace(hour=23).isoformat()
    return parse_event(
        calendar, {"start": start, "end": end, "summary": summary, **extra}, TZ
    )


def test_parse_event() -> None:
    event = all_day("Papier")
    assert event.all_day
    assert event.day == TUE
    assert event.start.isoformat() == "2026-11-16T23:00:00+00:00"
    assert event.end.isoformat() == "2026-11-17T23:00:00+00:00"

    event = timed("Dienst: Theke", "2026-11-20T19:00:00+01:00", location="Kult61")
    assert not event.all_day
    assert event.day == date(2026, 11, 20)
    assert event.start.isoformat() == "2026-11-20T18:00:00+00:00"
    assert event.location == "Kult61"
    assert CalendarEvent.from_dict(event.to_dict()) == event


def test_keyword_modes() -> None:
    rule = rule_of(
        muell_rule(
            filter={
                "keywords": {
                    "columns": ["x"],
                    "rows": [
                        {"match": "papier", "x": "contains"},
                        {"match": "Dienst:", "mode": "startswith", "x": "starts"},
                        {"match": r"^gelb(er)? sack$", "mode": "regex", "x": "regex"},
                    ],
                }
            }
        )
    )

    def hits(title: str) -> list[str] | None:
        rows = match_event(rule.filter, all_day(title))
        return None if rows is None else [row.values["x"] for row in rows]

    assert hits("Altpapier") == ["contains"]
    assert hits("PAPIER") == ["contains"]
    assert hits("Dienst: Theke") == ["starts"]
    assert hits("Kein Dienst: heute") is None
    assert hits("Gelber Sack") == ["regex"]
    assert hits("Gelber Sack und mehr") is None
    assert hits("Restmüll") is None
    assert hits("Dienst: Papier sortieren") == ["contains", "starts"]


def test_all_day_filter_and_no_keywords() -> None:
    rule = rule_of(muell_rule())
    assert match_event(rule.filter, all_day("Papier")) is not None
    assert (
        match_event(rule.filter, timed("Papier", "2026-11-17T08:00:00+01:00")) is None
    )

    birthdays = rule_of(muell_rule(filter={}))
    assert match_event(birthdays.filter, all_day("Anna")) == []
    assert (
        match_event(birthdays.filter, timed("Anna", "2026-11-17T08:00:00+01:00")) == []
    )


def test_rest_of_title() -> None:
    rule = rule_of(kult61_rule())
    event = timed("Dienst: Theke", "2026-11-20T19:00:00+01:00")
    assert rest_of_title(rule.filter, event) == "Theke"
    waste = rule_of(muell_rule())
    assert rest_of_title(waste.filter, all_day("Papier (4-wöchentlich)")) == (
        "(4-wöchentlich)"
    )
    assert rest_of_title(rule_of(muell_rule(filter={})).filter, all_day(" Anna ")) == (
        "Anna"
    )


def test_bundling() -> None:
    events = [
        all_day("Bio"),
        all_day("Papier"),
        all_day("Papier"),  # duplicate (same calendar, start and title)
        all_day("Sperrmüll"),  # no keyword
        all_day("Rest", date(2026, 11, 24)),
    ]
    bundled = build_occurrences(rule_of(muell_rule()), events)
    assert [(o.id, [e.summary for e in o.events]) for o in bundled] == [
        ("muell__20261117", ["Bio", "Papier"]),
        ("muell__20261124", ["Rest"]),
    ]

    single = build_occurrences(rule_of(muell_rule(bundle=False)), events)
    assert [[e.summary for e in o.events] for o in single] == [
        ["Bio"],
        ["Papier"],
        ["Rest"],
    ]
    assert len({o.id for o in single}) == 3
    assert all(o.id.startswith("muell__2026") for o in single)


def test_variables_single_and_plural() -> None:
    rule = rule_of(muell_rule())
    names = {WASTE: "Abfallkalender"}
    monday = date(2026, 11, 16)

    one = build_variables(
        rule,
        [all_day("Papier")],
        today=monday,
        tz=TZ,
        language="de",
        calendar_names=names,
    )
    assert one == {
        "titel": "Papier",
        "rest": "",
        "beschreibung": "",
        "ort": "",
        "kalender": "Abfallkalender",
        "wann": "morgen",
        "datum": "17.11.",
        "uhrzeit": "",
        "tonne": "Papiertonne",
        "tonnen": "Papiertonne",
        "farbe": "blau",
        "farben": "blau",
        "artikel": "die",
        "artikeln": "die",
    }

    events = [all_day("Papier"), all_day("Bio"), all_day("Gelb")]
    many = build_variables(rule, events, today=monday, tz=TZ, language="de")
    assert many["tonne"] == "Papiertonne"
    assert many["tonnen"] == "Papiertonne, Biotonne und gelben Sack"
    assert many["farben"] == "blau, grün und gelb"
    assert many["artikeln"] == "die und den"  # unique values only
    assert many["titel"] == "Papier, Bio und Gelb"
    assert many["kalender"] == WASTE

    english = build_variables(rule, events[:2], today=monday, tz=TZ, language="en")
    assert english["tonnen"] == "Papiertonne and Biotonne"
    assert english["wann"] == "tomorrow"
    assert english["datum"] == "Nov 17"


def test_variables_timed_event() -> None:
    rule = rule_of(kult61_rule())
    event = timed(
        "Dienst: Theke",
        "2026-11-20T19:00:00+01:00",
        description="Schlüssel bei Max",
        location="Kult61",
    )
    variables = build_variables(
        rule, [event], today=date(2026, 11, 16), tz=TZ, language="de"
    )
    assert variables["rest"] == "Theke"
    assert variables["uhrzeit"] == "19:00"
    assert variables["wann"] == "am Freitag"
    assert variables["beschreibung"] == "Schlüssel bei Max"
    assert variables["ort"] == "Kult61"
    assert (
        render("Denk an deinen Dienst {wann}: {rest}, ab {uhrzeit}.", variables)
        == "Denk an deinen Dienst am Freitag: Theke, ab 19:00."
    )


def test_describe_day() -> None:
    today = date(2026, 11, 16)  # Monday
    cases = {
        date(2026, 11, 16): ("heute", "today"),
        date(2026, 11, 17): ("morgen", "tomorrow"),
        date(2026, 11, 15): ("gestern", "yesterday"),
        date(2026, 11, 19): ("am Donnerstag", "on Thursday"),
        date(2026, 11, 22): ("am Sonntag", "on Sunday"),
        date(2026, 11, 23): ("am 23.11.", "on Nov 23"),
        date(2026, 12, 24): ("am 24.12.", "on Dec 24"),
        date(2026, 11, 10): ("am 10.11.", "on Nov 10"),
    }
    for day, (german, english) in cases.items():
        assert describe_day(day, today, "de") == german
        assert describe_day(day, today, "en-GB") == english


def test_render_and_join() -> None:
    variables = {"wann": "morgen", "tonnen": "Papiertonne und Biotonne"}
    assert render("{wann}: {tonnen}", variables) == "Morgen: Papiertonne und Biotonne"
    assert render("bitte {wann} raus", variables) == "bitte morgen raus"
    assert render("{unbekannt} {{ jinja }} {wann}", variables) == (
        "{unbekannt} {{ jinja }} morgen"
    )
    assert render(None, variables) == ""
    assert template_variables("{wann}: {tonnen} {{ x }}") == {"wann", "tonnen"}
    assert join_words(["a", "", "b", "a", "c"], "de") == "a, b und c"
    assert join_words([], "de") == ""
