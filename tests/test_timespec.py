"""Time specifications incl. daylight saving days (Europe/Berlin)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.laeutwerk.timespec import (
    KIND_EVENT_END,
    KIND_OFFSET,
    KIND_WALL,
    TimeSpec,
    local_instant,
    parse_timespec,
    resolve,
)

TZ = ZoneInfo("Europe/Berlin")


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("-1d 17:00", TimeSpec(KIND_WALL, days=-1, minute=17 * 60)),
        ("  -7D   9:05 ", TimeSpec(KIND_WALL, days=-7, minute=9 * 60 + 5)),
        ("+1d 08:00", TimeSpec(KIND_WALL, days=1, minute=8 * 60)),
        ("09:00", TimeSpec(KIND_WALL, minute=9 * 60)),
        ("event_day 12:00", TimeSpec(KIND_WALL, minute=12 * 60)),
        ("0d 00:00", TimeSpec(KIND_WALL)),
        ("-2h", TimeSpec(KIND_OFFSET, offset=timedelta(hours=-2))),
        ("-30m", TimeSpec(KIND_OFFSET, offset=timedelta(minutes=-30))),
        ("+45 m", TimeSpec(KIND_OFFSET, offset=timedelta(minutes=45))),
        ("-7d", TimeSpec(KIND_OFFSET, offset=timedelta(days=-7))),
        ("event_end", TimeSpec(KIND_EVENT_END)),
    ],
)
def test_parse(text: str, expected: TimeSpec) -> None:
    assert parse_timespec(text) == expected


@pytest.mark.parametrize(
    "text", ["", "bla", "25:00", "12:60", "-1d", "-1x", "17", "-1d17:00x", "1d 2h"]
)
def test_parse_invalid(text: str) -> None:
    if text == "-1d":
        assert parse_timespec(text).kind == KIND_OFFSET  # valid: exactly 24 h
        return
    with pytest.raises(ValueError, match="invalid"):
        parse_timespec(text)


def _all_day(day: date) -> dict:
    return {
        "day": day,
        "start": local_instant(day, 0, TZ),
        "end": local_instant(day + timedelta(days=1), 0, TZ),
        "tz": TZ,
    }


def test_resolve_wall_and_offset() -> None:
    event = _all_day(date(2026, 11, 17))
    # CET = UTC+1
    assert resolve(parse_timespec("-1d 17:00"), **event) == utc(2026, 11, 16, 16)
    assert resolve(parse_timespec("event_day 12:00"), **event) == utc(2026, 11, 17, 11)
    assert resolve(parse_timespec("event_end"), **event) == utc(2026, 11, 17, 23)
    assert resolve(parse_timespec("event_start"), **event) == utc(2026, 11, 16, 23)
    assert resolve(parse_timespec("-2h"), **event) == utc(2026, 11, 16, 21)

    start = datetime(2026, 11, 20, 19, 0, tzinfo=TZ)
    timed = {
        "day": start.date(),
        "start": start,
        "end": start + timedelta(hours=4),
        "tz": TZ,
    }
    assert resolve(parse_timespec("-2h"), **timed) == utc(2026, 11, 20, 16)
    assert resolve(parse_timespec("-1d 20:00"), **timed) == utc(2026, 11, 19, 19)
    assert resolve(parse_timespec("event_end"), **timed) == utc(2026, 11, 20, 22)


def test_spring_forward_day() -> None:
    """29 March 2026: 02:00-03:00 does not exist."""
    sunday = date(2026, 3, 29)
    # Reminder on Sunday for an event on Monday: 17:00 CEST = 15:00 UTC.
    monday = _all_day(date(2026, 3, 30))
    assert resolve(parse_timespec("-1d 17:00"), **monday) == utc(2026, 3, 29, 15)
    # Reminder on Saturday for an event on Sunday: 17:00 CET = 16:00 UTC.
    assert resolve(parse_timespec("-1d 17:00"), **_all_day(sunday)) == utc(
        2026, 3, 28, 16
    )
    # A time inside the gap becomes the first valid instant (03:00 CEST).
    assert resolve(parse_timespec("02:30"), **_all_day(sunday)) == utc(2026, 3, 29, 1)
    # The all-day event itself is only 23 h long.
    event = _all_day(sunday)
    assert event["end"] - event["start"] == timedelta(hours=23)
    # Elapsed offsets stay elapsed time: 2 h before 04:00 CEST is 01:00 CET.
    start = datetime(2026, 3, 29, 4, 0, tzinfo=TZ)
    timed = {"day": sunday, "start": start, "end": start, "tz": TZ}
    assert resolve(parse_timespec("-2h"), **timed) == utc(2026, 3, 29, 0)


def test_fall_back_day() -> None:
    """25 October 2026: 02:00-03:00 happens twice."""
    sunday = date(2026, 10, 25)
    event = _all_day(sunday)
    assert event["end"] - event["start"] == timedelta(hours=25)
    # A time inside the repeated hour means its first pass (CEST).
    assert resolve(parse_timespec("02:30"), **event) == utc(2026, 10, 25, 0, 30)
    # After the change: 17:00 CET = 16:00 UTC; the day before 17:00 CEST = 15:00.
    assert resolve(parse_timespec("17:00"), **event) == utc(2026, 10, 25, 16)
    assert resolve(parse_timespec("-1d 17:00"), **event) == utc(2026, 10, 24, 15)
    assert resolve(parse_timespec("-1d 17:00"), **_all_day(date(2026, 10, 26))) == utc(
        2026, 10, 25, 16
    )
