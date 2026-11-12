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
SIGNAL_LIGHT = "light_signal"
SIGNAL_ANNOUNCE = "announce"
SIGNAL_ACTION = "action"
SIGNAL_TYPES = (SIGNAL_NOTIFY, SIGNAL_LIGHT, SIGNAL_ANNOUNCE, SIGNAL_ACTION)

AUDIENCE_ALL = "all"
AUDIENCE_PRESENT = "present"
AUDIENCE_PERSONS = "persons"
AUDIENCE_ASSIGNEE = "assignee"
AUDIENCES = (AUDIENCE_ALL, AUDIENCE_PRESENT, AUDIENCE_PERSONS, AUDIENCE_ASSIGNEE)

ROTATION_FIXED = "fixed"
ROTATION_WEEKLY = "weekly"
ROTATION_PER_EVENT = "per_event"
ROTATION_AFTER_LAST = "after_last"
ROTATIONS = (ROTATION_FIXED, ROTATION_WEEKLY, ROTATION_PER_EVENT, ROTATION_AFTER_LAST)

# Pseudo source of "interval since done" rules (no calendar).
INTERVAL_SOURCE = "interval"
# Pseudo calendar of the synthetic event of "start trigger" rules.
TRIGGER_SOURCE = "trigger"

EFFECT_BLINK = "blink"
EFFECT_PULSE = "pulse"
EFFECTS = (EFFECT_BLINK, EFFECT_PULSE)

QUIET_SKIP = "skip"
QUIET_DEFER = "defer"
QUIET_MODES = (QUIET_SKIP, QUIET_DEFER)

MATCH_ALL = "all"
MATCH_ANY = "any"

WHEN_NOW = "now"

REPEAT_NONE = "none"
DEFAULT_REPEAT_MAX = 24

ACK_NOTIFY_ACTION = "notify_action"
ACK_TAG = "tag"
ACK_TRIGGER = "trigger"
ACK_TYPES = (ACK_NOTIFY_ACTION, ACK_TAG, ACK_TRIGGER)

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
    # Colour of the keyword (#rrggbb), e.g. the colour of the bin.
    color: str | None = None
    # Icon of the keyword (mdi:...), e.g. the bin symbol.
    icon: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KeywordRow:
        """Create from the stored (flat) form."""
        own = ("match", "mode", "color", "icon")
        return cls(
            match=data["match"],
            mode=data.get("mode", MATCH_CONTAINS),
            values={key: str(value) for key, value in data.items() if key not in own},
            color=data.get("color") or None,
            icon=data.get("icon") or None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the stored (flat) form."""
        data: dict[str, Any] = {"match": self.match}
        if self.mode != MATCH_CONTAINS:
            data["mode"] = self.mode
        if self.color:
            data["color"] = self.color
        if self.icon:
            data["icon"] = self.icon
        return {**data, **self.values}


def column_name(spec: Any) -> str:
    """Name of a keyword column (short form: the name, long form: a mapping)."""
    return str(spec["name"] if isinstance(spec, dict) else spec)


def column_plural(spec: Any) -> str | None:
    """Plural variable of a column: "<name>n" by default, None if switched off."""
    name = column_name(spec)
    plural = spec.get("plural", True) if isinstance(spec, dict) else True
    if plural is False:
        return None
    if plural is True or not plural:
        return f"{name}n"
    return str(plural)


def column_spec(name: str, plural: str | None) -> Any:
    """Short form (the name) while the plural is the default, else a mapping."""
    if plural == f"{name}n":
        return name
    return {"name": name, "plural": plural if plural is not None else False}


@dataclass(slots=True)
class Filter:
    """Which events of the sources belong to a rule."""

    all_day: bool = False
    columns: list[str] = field(default_factory=list)  # names
    rows: list[KeywordRow] = field(default_factory=list)
    # Plural variable per column name (None: no plural variable).
    plurals: dict[str, str | None] = field(default_factory=dict)

    def plural(self, column: str) -> str | None:
        """Plural variable of a column (default "<name>n")."""
        return self.plurals.get(column, f"{column}n")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Filter:
        """Create from the stored form."""
        keywords = data.get("keywords") or {}
        specs = list(keywords.get("columns", []))
        return cls(
            all_day=bool(data.get("all_day", False)),
            columns=[column_name(spec) for spec in specs],
            rows=[KeywordRow.from_dict(row) for row in keywords.get("rows", [])],
            plurals={column_name(spec): column_plural(spec) for spec in specs},
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the stored form."""
        return {
            "all_day": self.all_day,
            "keywords": {
                "columns": [
                    column_spec(name, self.plural(name)) for name in self.columns
                ],
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

    @property
    def opportunity(self) -> Any:
        """Trigger configuration of an "on opportunity" signal, else None."""
        return self.when.get("opportunity") if isinstance(self.when, dict) else None

    @property
    def stage(self) -> int:
        """Escalation stage from which the signal is active."""
        return int(self.config.get("stage", 0))

    @property
    def every_stage(self) -> bool:
        """Also sent at every reached escalation stage."""
        return bool(self.config.get("every_stage", False))

    @property
    def manual_only(self) -> bool:
        """Only real operation counts as opportunity (no automations)."""
        return isinstance(self.when, dict) and bool(self.when.get("manual_only"))

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
    # Editable headline of a reminder ({variables}); None: the card's default.
    headline: str | None = None
    headline_plural: str | None = None
    enabled: bool = True
    filter: Filter = field(default_factory=Filter)
    signals: list[Signal] = field(default_factory=list)
    acknowledge: list[dict[str, Any]] = field(default_factory=list)
    ack_label: str | None = None
    repeat: Any = REPEAT_NONE
    bundle: bool = True
    expire: str = DEFAULT_EXPIRE
    # 0.6: {every (days), start (date)} – due again n days after done.
    interval: dict[str, Any] | None = None
    # 0.6: {conditions, match, season: {from, to}} – rule only active then.
    activation: dict[str, Any] | None = None
    # 0.6: Home Assistant actions run when a reminder is acknowledged.
    on_done: list[dict[str, Any]] = field(default_factory=list)
    # 0.10: actions run when a reminder becomes missed / after every remind.
    on_missed: list[dict[str, Any]] = field(default_factory=list)
    on_reminded: list[dict[str, Any]] = field(default_factory=list)
    # 0.6: {persons, rotation} – who is responsible ({zustaendig}).
    assignee: dict[str, Any] | None = None
    # 0.6: escalation stages [{after}] – signals with "stage: n" start then.
    escalation: list[dict[str, Any]] = field(default_factory=list)
    # 0.9: days the calendars are read ahead for this rule.
    lookahead_days: int = 14
    # 0.9: shown in the card overview (entities and signals are unaffected).
    visible: bool = True
    # 0.9: Home Assistant triggers that start a reminder (instead of a calendar).
    start_triggers: list[dict[str, Any]] = field(default_factory=list)
    # 0.9: {message, clear_after} – confirmation to whoever acknowledged.
    confirm: dict[str, Any] | None = None
    # 0.9.2: acknowledging a planned reminder before its time.
    early: dict[str, Any] = field(
        default_factory=lambda: {"mode": "hours", "hours": 24}
    )
    # 0.9.2: {message, clear_after} – push after a too early attempt.
    early_feedback: dict[str, Any] | None = None

    @property
    def trigger_mode(self) -> bool:
        """Whether reminders are started by triggers."""
        return bool(self.start_triggers)

    @property
    def repeat_every(self) -> int | None:
        """Minutes between repetitions while a reminder is open."""
        return self.repeat.get("every") if isinstance(self.repeat, dict) else None

    @property
    def repeat_max(self) -> int:
        """Maximum number of repetitions per reminder."""
        if isinstance(self.repeat, dict):
            return int(self.repeat.get("max", DEFAULT_REPEAT_MAX))
        return 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rule:
        """Create from validated data."""
        return cls(
            id=data["id"],
            name=data["name"],
            sources=list(data["sources"]),
            reminders=[item["at"] for item in data.get("reminders", [])],
            icon=data.get("icon"),
            color=data.get("color"),
            headline=data.get("headline") or None,
            headline_plural=data.get("headline_plural") or None,
            enabled=bool(data.get("enabled", True)),
            filter=Filter.from_dict(data.get("filter") or {}),
            signals=[Signal.from_dict(item) for item in data.get("signals", [])],
            acknowledge=[dict(item) for item in data.get("acknowledge", [])],
            ack_label=data.get("ack_label"),
            repeat=data.get("repeat", REPEAT_NONE),
            bundle=bool(data.get("bundle", True)),
            expire=data.get("expire", DEFAULT_EXPIRE),
            interval=data.get("interval"),
            activation=data.get("activation"),
            on_done=list(data.get("on_done") or []),
            on_missed=list(data.get("on_missed") or []),
            on_reminded=list(data.get("on_reminded") or []),
            assignee=data.get("assignee"),
            escalation=list(data.get("escalation") or []),
            lookahead_days=int(data.get("lookahead_days", 14)),
            visible=bool(data.get("visible", True)),
            start_triggers=list(data.get("start_triggers") or []),
            confirm=data.get("confirm"),
            early=dict(data.get("early") or {"mode": "hours", "hours": 24}),
            early_feedback=data.get("early_feedback"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the stored form."""
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "color": self.color,
            "headline": self.headline,
            "headline_plural": self.headline_plural,
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
            "interval": self.interval,
            "activation": self.activation,
            "on_done": list(self.on_done),
            "on_missed": list(self.on_missed),
            "on_reminded": list(self.on_reminded),
            "assignee": self.assignee,
            "escalation": list(self.escalation),
            "lookahead_days": self.lookahead_days,
            "visible": self.visible,
            "start_triggers": list(self.start_triggers),
            "confirm": self.confirm,
            "early": dict(self.early),
            "early_feedback": self.early_feedback,
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
    # Person entity of whoever acknowledged (None: a user without person).
    acknowledged_person: str | None = None
    signals_sent: dict[str, int] = field(default_factory=dict)
    # Last time each signal was sent (minimum interval).
    signal_last: dict[str, datetime] = field(default_factory=dict)
    # Signals held back by a quiet time: signal id -> when to send them.
    deferred: dict[str, datetime] = field(default_factory=dict)
    # "Remind me later": planned again until this time.
    snoozed_until: datetime | None = None
    # Repetitions while reminding: how many and when last reminded.
    repeats: int = 0
    last_reminded: datetime | None = None
    # Escalation stage reached (0 = the reminder itself).
    stage: int = 0
    # Number of reminders sent (first remind = 1, then repeats, stages, snooze).
    nr: int = 0
    # Responsible person (entity id), fixed when the reminder is created.
    assignee: str | None = None
    # Original person if a substitute took over at the first reminder.
    substitute_for: str | None = None
    # Name of whoever caused a trigger-started reminder ({person}).
    trigger_person: str = ""

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
            acknowledged_person=data.get("acknowledged_person"),
            signals_sent=dict(data.get("signals_sent", {})),
            signal_last={
                key: _parse_dt(value)
                for key, value in data.get("signal_last", {}).items()
            },
            deferred={
                key: _parse_dt(value) for key, value in data.get("deferred", {}).items()
            },
            snoozed_until=_parse_opt(data.get("snoozed_until")),
            repeats=int(data.get("repeats", 0)),
            last_reminded=_parse_opt(data.get("last_reminded")),
            stage=int(data.get("stage", 0)),
            nr=int(data.get("nr", 0)),
            assignee=data.get("assignee"),
            substitute_for=data.get("substitute_for"),
            trigger_person=data.get("trigger_person", ""),
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
            "acknowledged_person": self.acknowledged_person,
            "signals_sent": dict(self.signals_sent),
            "signal_last": {
                key: value.isoformat() for key, value in self.signal_last.items()
            },
            "deferred": {
                key: value.isoformat() for key, value in self.deferred.items()
            },
            "snoozed_until": _format_opt(self.snoozed_until),
            "repeats": self.repeats,
            "last_reminded": _format_opt(self.last_reminded),
            "stage": self.stage,
            "nr": self.nr,
            "assignee": self.assignee,
            "substitute_for": self.substitute_for,
            "trigger_person": self.trigger_person,
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
