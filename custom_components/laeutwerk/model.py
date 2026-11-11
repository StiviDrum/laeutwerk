"""Data model: rules (configuration) and reminders (runtime state)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from homeassistant.util import dt as dt_util

MATCH_CONTAINS = "contains"
MATCH_STARTSWITH = "startswith"
MATCH_REGEX = "regex"
MATCH_MODES = (MATCH_CONTAINS, MATCH_STARTSWITH, MATCH_REGEX)

SIGNAL_NOTIFY = "notify"
SIGNAL_TYPES = (SIGNAL_NOTIFY,)

WHEN_NOW = "now"

REPEAT_NONE = "none"

ACK_NOTIFY_ACTION = "notify_action"

STATE_PLANNED = "planned"
STATE_REMINDED = "reminded"
STATE_DONE = "done"
STATE_MISSED = "missed"
STATE_INACTIVE = "inactive"
OPEN_STATES = (STATE_PLANNED, STATE_REMINDED)

DEFAULT_EXPIRE = "event_end"


@dataclass(slots=True)
class KeywordRow:
    """One row of the keyword table: what to look for and its column values."""

    match: str
    mode: str = MATCH_CONTAINS
    values: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KeywordRow:
        """Create from the stored (flat) form."""
        return cls(
            match=data["match"],
            mode=data.get("mode", MATCH_CONTAINS),
            values={
                key: str(value)
                for key, value in data.items()
                if key not in ("match", "mode")
            },
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the stored (flat) form."""
        data: dict[str, Any] = {"match": self.match}
        if self.mode != MATCH_CONTAINS:
            data["mode"] = self.mode
        return {**data, **self.values}


@dataclass(slots=True)
class Filter:
    """Which events of the sources belong to a rule."""

    all_day: bool = False
    columns: list[str] = field(default_factory=list)
    rows: list[KeywordRow] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Filter:
        """Create from the stored form."""
        keywords = data.get("keywords") or {}
        return cls(
            all_day=bool(data.get("all_day", False)),
            columns=list(keywords.get("columns", [])),
            rows=[KeywordRow.from_dict(row) for row in keywords.get("rows", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the stored form."""
        return {
            "all_day": self.all_day,
            "keywords": {
                "columns": list(self.columns),
                "rows": [row.to_dict() for row in self.rows],
            },
        }


@dataclass(slots=True)
class Signal:
    """One signal of a rule; ``config`` holds the fields of its type."""

    id: str
    type: str
    enabled: bool = True
    when: Any = WHEN_NOW
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Signal:
        """Create from the stored (flat) form."""
        return cls(
            id=data["id"],
            type=data["type"],
            enabled=bool(data.get("enabled", True)),
            when=data.get("when", WHEN_NOW),
            config={
                key: value
                for key, value in data.items()
                if key not in ("id", "type", "enabled", "when")
            },
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the stored (flat) form."""
        return {
            "id": self.id,
            "type": self.type,
            "enabled": self.enabled,
            "when": self.when,
            **self.config,
        }


@dataclass(slots=True)
class Rule:
    """A rule: source, filter, reminder times, signals and acknowledgement."""

    id: str
    name: str
    sources: list[str]
    reminders: list[str]
    icon: str | None = None
    color: str | None = None
    enabled: bool = True
    filter: Filter = field(default_factory=Filter)
    signals: list[Signal] = field(default_factory=list)
    acknowledge: list[dict[str, Any]] = field(default_factory=list)
    ack_label: str | None = None
    repeat: Any = REPEAT_NONE
    bundle: bool = True
    expire: str = DEFAULT_EXPIRE

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rule:
        """Create from validated data."""
        return cls(
            id=data["id"],
            name=data["name"],
            sources=list(data["sources"]),
            reminders=[item["at"] for item in data["reminders"]],
            icon=data.get("icon"),
            color=data.get("color"),
            enabled=bool(data.get("enabled", True)),
            filter=Filter.from_dict(data.get("filter") or {}),
            signals=[Signal.from_dict(item) for item in data.get("signals", [])],
            acknowledge=[dict(item) for item in data.get("acknowledge", [])],
            ack_label=data.get("ack_label"),
            repeat=data.get("repeat", REPEAT_NONE),
            bundle=bool(data.get("bundle", True)),
            expire=data.get("expire", DEFAULT_EXPIRE),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the stored form."""
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "color": self.color,
            "enabled": self.enabled,
            "sources": list(self.sources),
            "filter": self.filter.to_dict(),
            "reminders": [{"at": at} for at in self.reminders],
            "signals": [signal.to_dict() for signal in self.signals],
            "acknowledge": [dict(item) for item in self.acknowledge],
            "ack_label": self.ack_label,
            "repeat": self.repeat,
            "bundle": self.bundle,
            "expire": self.expire,
        }


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """A calendar event as read from ``calendar.get_events``."""

    calendar: str
    summary: str
    start: datetime  # UTC
    end: datetime  # UTC
    all_day: bool
    day: date  # local day of the start
    description: str = ""
    location: str = ""

    @property
    def key(self) -> str:
        """Identity of the event (calendars expose no stable uid)."""
        return f"{self.calendar}|{self.start.isoformat()}|{self.summary}"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalendarEvent:
        """Create from the stored form."""
        return cls(
            calendar=data["calendar"],
            summary=data["summary"],
            start=_parse_dt(data["start"]),
            end=_parse_dt(data["end"]),
            all_day=bool(data["all_day"]),
            day=date.fromisoformat(data["day"]),
            description=data.get("description", ""),
            location=data.get("location", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the stored form."""
        return {
            "calendar": self.calendar,
            "summary": self.summary,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "all_day": self.all_day,
            "day": self.day.isoformat(),
            "description": self.description,
            "location": self.location,
        }


@dataclass(slots=True)
class Reminder:
    """Runtime state of one reminder (one event or one bundle of a day)."""

    id: str
    rule_id: str
    day: date
    start: datetime  # UTC, earliest event start
    end: datetime  # UTC, latest event end
    events: list[CalendarEvent]
    state: str = STATE_PLANNED
    # Reminder times (their text form) that were already sent.
    fired: list[str] = field(default_factory=list)
    reminded_at: datetime | None = None
    finished_at: datetime | None = None  # acknowledged or missed
    acknowledged_by: str | None = None
    acknowledged_via: str | None = None
    signals_sent: dict[str, int] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        """Not yet acknowledged or missed."""
        return self.state in OPEN_STATES

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Reminder:
        """Create from the stored form."""
        return cls(
            id=data["id"],
            rule_id=data["rule_id"],
            day=date.fromisoformat(data["day"]),
            start=_parse_dt(data["start"]),
            end=_parse_dt(data["end"]),
            events=[CalendarEvent.from_dict(item) for item in data["events"]],
            state=data.get("state", STATE_PLANNED),
            fired=list(data.get("fired", [])),
            reminded_at=_parse_opt(data.get("reminded_at")),
            finished_at=_parse_opt(data.get("finished_at")),
            acknowledged_by=data.get("acknowledged_by"),
            acknowledged_via=data.get("acknowledged_via"),
            signals_sent=dict(data.get("signals_sent", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the stored form."""
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "day": self.day.isoformat(),
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "events": [event.to_dict() for event in self.events],
            "state": self.state,
            "fired": list(self.fired),
            "reminded_at": _format_opt(self.reminded_at),
            "finished_at": _format_opt(self.finished_at),
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_via": self.acknowledged_via,
            "signals_sent": dict(self.signals_sent),
        }


def _parse_dt(value: str) -> datetime:
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        raise ValueError(f"invalid datetime '{value}'")
    return dt_util.as_utc(parsed)


def _parse_opt(value: str | None) -> datetime | None:
    return _parse_dt(value) if value else None


def _format_opt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
