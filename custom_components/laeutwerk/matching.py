"""Pure logic: which events match a rule, bundling and text variables."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
import hashlib
import re
from typing import Any

from homeassistant.util import dt as dt_util

from .colors import color_hex
from .model import (
    INTERVAL_SOURCE,
    MATCH_REGEX,
    MATCH_STARTSWITH,
    CalendarEvent,
    Filter,
    KeywordRow,
    Rule,
)
from .timespec import local_instant

# Variables every reminder has (SPEC B4); column names must not use them.
EVENT_VARIABLES = (
    "titel",
    "rest",
    "beschreibung",
    "ort",
    "kalender",
    "wann",
    "datum",
    "uhrzeit",
    "person",
    "zustaendig",
)

_VARIABLE = re.compile(r"(?<!\{)\{([^\W\d]\w*)\}(?!\})")
_SEPARATORS = " \t:-–—,;|/+&"

_WEEKDAYS = {
    "de": [
        "Montag",
        "Dienstag",
        "Mittwoch",
        "Donnerstag",
        "Freitag",
        "Samstag",
        "Sonntag",
    ],
    "en": [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ],
}
_MONTHS_EN = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]


@dataclass(frozen=True, slots=True)
class Occurrence:
    """Events of one rule that become one reminder."""

    id: str
    day: date
    start: datetime
    end: datetime
    events: tuple[CalendarEvent, ...]


def _lang(language: str | None) -> str:
    return "de" if (language or "").lower().startswith("de") else "en"


def parse_event(calendar: str, raw: Mapping[str, Any], tz: tzinfo) -> CalendarEvent:
    """Convert an event of the ``calendar.get_events`` response."""
    start_raw, end_raw = str(raw["start"]), str(raw["end"])
    all_day = "T" not in start_raw
    if all_day:
        day = date.fromisoformat(start_raw)
        end_day = date.fromisoformat(end_raw[:10])
        start = local_instant(day, 0, tz)
        end = local_instant(max(end_day, day + timedelta(days=1)), 0, tz)
    else:
        start_local = datetime.fromisoformat(start_raw)
        end_local = datetime.fromisoformat(end_raw)
        if start_local.tzinfo is None:
            start_local = start_local.replace(tzinfo=tz)
        if end_local.tzinfo is None:
            end_local = end_local.replace(tzinfo=tz)
        start, end = start_local.astimezone(UTC), end_local.astimezone(UTC)
        day = start.astimezone(tz).date()
    return CalendarEvent(
        calendar=calendar,
        summary=str(raw.get("summary") or ""),
        start=start,
        end=max(end, start),
        all_day=all_day,
        day=day,
        description=str(raw.get("description") or ""),
        location=str(raw.get("location") or ""),
    )


def _row_span(row: KeywordRow, title: str) -> tuple[int, int] | None:
    """Position of the row's keyword in a title, None if it does not match."""
    if row.mode == MATCH_REGEX:
        try:
            found = re.search(row.match, title, re.IGNORECASE)
        except re.error:
            return None
        return found.span() if found else None
    needle, haystack = row.match.casefold(), title.casefold()
    if not needle:
        return None
    if row.mode == MATCH_STARTSWITH:
        return (0, len(needle)) if haystack.startswith(needle) else None
    index = haystack.find(needle)
    return (index, index + len(needle)) if index >= 0 else None


def match_event(flt: Filter, event: CalendarEvent) -> list[KeywordRow] | None:
    """Rows of the keyword table an event matches.

    ``None``: the event does not belong to the rule. Without keyword rows
    every event matches (empty list).
    """
    if flt.all_day and not event.all_day:
        return None
    if not flt.rows:
        return []
    hits = [row for row in flt.rows if _row_span(row, event.summary) is not None]
    return hits or None


def rest_of_title(flt: Filter, event: CalendarEvent) -> str:
    """Title without the first matching keyword (``{rest}``)."""
    title = event.summary
    for row in flt.rows:
        if (span := _row_span(row, title)) is not None:
            rest = (title[: span[0]] + " " + title[span[1] :]).strip(_SEPARATORS)
            return " ".join(rest.split())
    return title.strip()


def build_occurrences(rule: Rule, events: Iterable[CalendarEvent]) -> list[Occurrence]:
    """Match events and group them into reminders (one per day if bundled)."""
    groups: dict[str, list[CalendarEvent]] = {}
    seen: set[str] = set()
    for event in sorted(events, key=lambda e: (e.start, e.calendar, e.summary)):
        if event.key in seen:
            continue
        if (
            event.calendar != INTERVAL_SOURCE
            and match_event(rule.filter, event) is None
        ):
            continue
        seen.add(event.key)
        key = f"{rule.id}__{event.day:%Y%m%d}"
        if not rule.bundle:
            digest = hashlib.sha256(event.key.encode()).hexdigest()[:8]
            key = f"{key}_{digest}"
        groups.setdefault(key, []).append(event)
    return [
        Occurrence(
            id=key,
            day=items[0].day,
            start=min(e.start for e in items),
            end=max(e.end for e in items),
            events=tuple(items),
        )
        for key, items in groups.items()
    ]


def sample_occurrence(rule: Rule) -> Occurrence:
    """Made-up event for tomorrow (testing a signal without a real event)."""
    tz = dt_util.get_default_time_zone()
    day = dt_util.now().date() + timedelta(days=1)
    title = rule.filter.rows[0].match if rule.filter.rows else rule.name
    if rule.filter.rows and rule.filter.rows[0].mode == MATCH_REGEX:
        title = rule.name
    event = CalendarEvent(
        calendar=rule.sources[0],
        summary=title,
        start=local_instant(day, 0, tz),
        end=local_instant(day + timedelta(days=1), 0, tz),
        all_day=True,
        day=day,
    )
    return Occurrence(
        id="sample", day=day, start=event.start, end=event.end, events=(event,)
    )


def join_words(words: Iterable[str], language: str | None) -> str:
    """Join unique, non-empty words: "a, b und c"."""
    unique = list(dict.fromkeys(word for word in words if word))
    if len(unique) <= 1:
        return unique[0] if unique else ""
    conjunction = "und" if _lang(language) == "de" else "and"
    return f"{', '.join(unique[:-1])} {conjunction} {unique[-1]}"


def describe_day(day: date, today: date, language: str | None) -> str:
    """Relative wording of a day: heute / morgen / am Donnerstag / am 24.12."""
    lang = _lang(language)
    delta = (day - today).days
    if lang == "de":
        fixed = {0: "heute", 1: "morgen", -1: "gestern"}
        if delta in fixed:
            return fixed[delta]
        if 1 < delta < 7:
            return f"am {_WEEKDAYS['de'][day.weekday()]}"
        return f"am {format_date(day, lang)}"
    fixed = {0: "today", 1: "tomorrow", -1: "yesterday"}
    if delta in fixed:
        return fixed[delta]
    if 1 < delta < 7:
        return f"on {_WEEKDAYS['en'][day.weekday()]}"
    return f"on {format_date(day, lang)}"


def format_date(day: date, language: str | None) -> str:
    """Short date: 24.12. / Dec 24."""
    if _lang(language) == "de":
        return f"{day.day}.{day.month}."
    return f"{_MONTHS_EN[day.month - 1]} {day.day}"


def hits_of(rule: Rule, events: Iterable[CalendarEvent]) -> list[KeywordRow]:
    """Return the unique matching keyword rows of some events, in event order."""
    hits: list[KeywordRow] = []
    for event in events:
        for row in match_event(rule.filter, event) or []:
            if not any(row is known for known in hits):
                hits.append(row)
    return hits


COLOR_COLUMNS = ("farbe", "color", "colour")


def keyword_colors(rule: Rule, events: Iterable[CalendarEvent]) -> list[str]:
    """Own colours (#rrggbb) of the matching keyword rows, unique, in order."""
    colors = [row.color for row in hits_of(rule, events) if row.color]
    return list(dict.fromkeys(colors))


def hit_colors(rule: Rule, events: Iterable[CalendarEvent]) -> list[str]:
    """Colours (#rrggbb) of the matching rows, for the dots in the card.

    The keywords' own colours; for older tables the column a light signal
    uses (``color_from``), else a column named farbe / color.
    """
    events = list(events)
    if own := keyword_colors(rule, events):
        return own
    column = next(
        (s.config["color_from"] for s in rule.signals if s.config.get("color_from")),
        None,
    ) or next((c for c in COLOR_COLUMNS if c in rule.filter.columns), None)
    if column is None:
        return []
    colors = [color_hex(row.values.get(column)) for row in hits_of(rule, events)]
    return [color for color in colors if color]


def hit_badges(rule: Rule, events: Iterable[CalendarEvent]) -> list[dict[str, Any]]:
    """Icon and colour per matching keyword row, identical pairs removed.

    Colour: the row's own, else the legacy column colour (``color_from`` or a
    column named farbe / color). The card adds the rule's icon / colour as the
    fallback.
    """
    rows = hits_of(rule, list(events))
    column = next(
        (s.config["color_from"] for s in rule.signals if s.config.get("color_from")),
        None,
    ) or next((c for c in COLOR_COLUMNS if c in rule.filter.columns), None)
    badges: list[dict[str, Any]] = []
    for row in rows:
        color = row.color or (color_hex(row.values.get(column)) if column else None)
        badge = {"icon": row.icon, "color": color}
        if badge not in badges:
            badges.append(badge)
    return badges


def render_headline(
    rule: Rule, events: Iterable[CalendarEvent], variables: Mapping[str, str]
) -> str | None:
    """Render the rule headline (plural variant for several hits); None if unset."""
    events = list(events)
    template = (
        rule.headline_plural
        if rule.headline_plural and is_plural(rule, events)
        else rule.headline
    )
    return render(template, variables) if template else None


def is_plural(rule: Rule, events: Iterable[CalendarEvent]) -> bool:
    """Whether the plural text variants apply (more than one hit / event)."""
    events = list(events)
    if rule.filter.rows:
        return len(hits_of(rule, events)) > 1
    return len(events) > 1


def build_variables(
    rule: Rule,
    events: Iterable[CalendarEvent],
    *,
    today: date,
    tz: tzinfo,
    language: str | None,
    calendar_names: Mapping[str, str] | None = None,
    assignee: str | None = None,
) -> dict[str, str]:
    """Variables of a reminder (SPEC B4)."""
    events = list(events)
    if not events:
        return {}
    first = events[0]
    names = calendar_names or {}
    variables = {
        "titel": join_words((e.summary for e in events), language),
        "rest": join_words((rest_of_title(rule.filter, e) for e in events), language),
        "beschreibung": first.description,
        "ort": first.location,
        "kalender": names.get(first.calendar, first.calendar),
        "wann": describe_day(first.day, today, language),
        "datum": format_date(first.day, language),
        "uhrzeit": "" if first.all_day else f"{first.start.astimezone(tz):%H:%M}",
    }
    if assignee is not None:
        variables["zustaendig"] = assignee
    hits = hits_of(rule, events)
    for column in rule.filter.columns:
        values = [row.values.get(column, "") for row in hits]
        plural = rule.filter.plural(column)
        if plural is None:
            # No plural variable: the unique values of a bundle, joined.
            variables[column] = join_words(values, language)
        else:
            variables[column] = values[0] if values else ""
            variables[plural] = join_words(values, language)
    return variables


def render(
    template: str | None, variables: Mapping[str, str], *, capitalize: bool = True
) -> str:
    """Replace ``{name}`` placeholders; unknown names stay as they are.

    Texts that start with a variable get a capital first letter ("{wann}: …"
    -> "Morgen: …"); identifiers such as tag ids use ``capitalize=False``.
    """
    if not template:
        return ""
    text = _VARIABLE.sub(lambda m: variables.get(m[1], m[0]), template)
    if capitalize and template.startswith("{"):
        text = text[:1].upper() + text[1:]
    return text


def template_variables(template: str | None) -> set[str]:
    """Names of the placeholders used in a text."""
    return set(_VARIABLE.findall(template or ""))
