"""Seed the local dev instance (./config) with the reference calendars.

Creates the local calendars "Abfallkalender" and "Kult61" (recurring events,
so they never run out) and the Läutwerk config entry. Existing files are left
alone; pass --force to rewrite the calendar files.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sys

STORAGE = Path(__file__).parent.parent / "config" / ".storage"

# (summary, first day, every n weeks) – all-day events.
# Papier + Bio share a day every 4 weeks -> bundling case.
WASTE = [
    ("Papier", "20261103", 4),
    ("Bio", "20261103", 2),
    ("Rest", "20261110", 2),
    ("Gelb", "20261112", 4),
]
# (summary, start, end, every n weeks) – local time Europe/Berlin.
KULT61 = [
    ("Dienst: Theke", "20261106T190000", "20261106T230000", 1),
    ("Dienst: Kasse", "20261114T180000", "20261114T220000", 3),
    ("Plenum", "20261109T193000", "20261109T210000", 4),
]

CALENDARS = {"Abfallkalender": "abfallkalender", "Kult61": "kult61"}


def _ics(events: list[str]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//laeutwerk//dev seed//EN",
        "VERSION:2.0",
        *events,
        "END:VCALENDAR",
        "",
    ]
    return "\r\n".join(lines)


def _event(uid: str, summary: str, start: str, end: str, weeks: int) -> str:
    all_day = "T" not in start
    kind = ";VALUE=DATE" if all_day else ";TZID=Europe/Berlin"
    return "\r\n".join(
        [
            "BEGIN:VEVENT",
            f"UID:{uid}@laeutwerk-dev",
            "DTSTAMP:20261101T000000Z",
            f"DTSTART{kind}:{start}",
            f"DTEND{kind}:{end}",
            f"SUMMARY:{summary}",
            f"RRULE:FREQ=WEEKLY;INTERVAL={weeks}",
            "END:VEVENT",
        ]
    )


def _next_day(day: str) -> str:
    date = datetime.strptime(day, "%Y%m%d").date()
    return date.fromordinal(date.toordinal() + 1).strftime("%Y%m%d")


def _entry(domain: str, title: str, data: dict[str, str], num: int) -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "created_at": now,
        "data": data,
        "disabled_by": None,
        "discovery_keys": {},
        "domain": domain,
        "entry_id": f"01LAEUTWERKDEVSEED{num:08d}",
        "minor_version": 1,
        "modified_at": now,
        "options": {},
        "pref_disable_new_entities": False,
        "pref_disable_polling": False,
        "source": "user",
        "subentries": [],
        "title": title,
        "unique_id": None,
        "version": 1,
    }


def main() -> None:
    force = "--force" in sys.argv
    STORAGE.mkdir(parents=True, exist_ok=True)

    files = {
        "abfallkalender": _ics(
            [
                _event(f"waste-{i}", name, day, _next_day(day), weeks)
                for i, (name, day, weeks) in enumerate(WASTE)
            ]
        ),
        "kult61": _ics(
            [
                _event(f"kult-{i}", name, start, end, weeks)
                for i, (name, start, end, weeks) in enumerate(KULT61)
            ]
        ),
    }
    for key, content in files.items():
        path = STORAGE / f"local_calendar.{key}.ics"
        if force or not path.exists():
            path.write_text(content, encoding="utf-8", newline="")
            print(f"wrote {path.name}")

    entries_path = STORAGE / "core.config_entries"
    if entries_path.exists():
        return  # instance already initialised – add missing calendars via the UI
    entries = [
        _entry("local_calendar", name, {"calendar_name": name, "storage_key": key}, num)
        for num, (name, key) in enumerate(CALENDARS.items())
    ]
    entries.append(_entry("laeutwerk", "Läutwerk", {}, len(entries)))
    entries_path.write_text(
        json.dumps(
            {
                "version": 1,
                "minor_version": 5,
                "key": "core.config_entries",
                "data": {"entries": entries},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("wrote core.config_entries (local calendars + Läutwerk)")


if __name__ == "__main__":
    main()
