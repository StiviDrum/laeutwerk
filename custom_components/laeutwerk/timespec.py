"""Time specifications relative to an event (pure, DST safe).

Reminder times (``at``) and the expiry (``expire``) are short strings:

==================  =========================================================
``-1d 17:00``       wall-clock time, n days before (-) / after (+) the event day
``17:00``           wall-clock time on the event day (same as ``0d 17:00``)
``event_day 12:00`` the same, readable form
``-2h`` ``-30m``    elapsed time before (-) / after (+) the event start
``-7d``             exactly n * 24 h before / after the event start
``event_start``     the event start
``event_end``       the event end (all-day events: end of the last day)
==================  =========================================================

Wall-clock times follow the local clock across daylight saving changes: a
time inside the skipped hour in March becomes the first valid instant after
the gap, a time inside the repeated hour in October means its first pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
import re

KIND_WALL = "wall"
KIND_OFFSET = "offset"
KIND_EVENT_START = "event_start"
KIND_EVENT_END = "event_end"

_WALL = re.compile(r"^(?:(?:([+-]?\d{1,3})d|event_day)\s+)?(\d{1,2}):(\d{2})$")
_OFFSET = re.compile(r"^([+-]?)(\d{1,4})\s*([dhm])$")
_UNITS = {"d": "days", "h": "hours", "m": "minutes"}


@dataclass(frozen=True, slots=True)
class TimeSpec:
    """Parsed time specification."""

    kind: str
    days: int = 0
    minute: int = 0
    offset: timedelta = timedelta()


def parse_timespec(text: str) -> TimeSpec:
    """Parse a time specification, raise ``ValueError`` if it is invalid."""
    value = " ".join(str(text).strip().lower().split())
    if value in (KIND_EVENT_START, KIND_EVENT_END):
        return TimeSpec(value)
    if match := _WALL.match(value):
        hour, minute = int(match[2]), int(match[3])
        if hour > 23 or minute > 59:
            raise ValueError(f"invalid time of day in '{text}'")
        return TimeSpec(KIND_WALL, days=int(match[1] or 0), minute=hour * 60 + minute)
    if match := _OFFSET.match(value):
        amount = int(match[2]) * (-1 if match[1] == "-" else 1)
        return TimeSpec(KIND_OFFSET, offset=timedelta(**{_UNITS[match[3]]: amount}))
    raise ValueError(
        f"invalid time '{text}' (examples: '-1d 17:00', '09:00', '-2h', "
        "'event_day 12:00', 'event_end')"
    )


def local_instant(day: date, minute: int, tz: tzinfo) -> datetime:
    """UTC instant of a wall-clock minute on a local date (DST safe)."""
    naive = datetime.combine(day, time(minute // 60, minute % 60))
    normalised = naive.replace(tzinfo=tz, fold=0).astimezone(UTC)
    if normalised.astimezone(tz).replace(tzinfo=None) == naive:
        return normalised  # exists (first pass if the hour is repeated)
    # Inside a spring-forward gap: first valid instant after the gap.
    candidate = naive.replace(tzinfo=tz, fold=1).astimezone(UTC)
    while candidate.astimezone(tz).replace(tzinfo=None) < naive:
        candidate += timedelta(minutes=1)
    return candidate


def resolve(
    spec: TimeSpec, *, day: date, start: datetime, end: datetime, tz: tzinfo
) -> datetime:
    """UTC instant of a specification for an event (local start day, start, end)."""
    if spec.kind == KIND_WALL:
        return local_instant(day + timedelta(days=spec.days), spec.minute, tz)
    if spec.kind == KIND_OFFSET:
        return start.astimezone(UTC) + spec.offset
    if spec.kind == KIND_EVENT_END:
        return end.astimezone(UTC)
    return start.astimezone(UTC)
