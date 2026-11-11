"""Durations as entered by users: minutes, or '30m' / '3h' / '1d'."""

from __future__ import annotations

import re
from typing import Any

from .compat import vol

_UNITS = {"": 1, "m": 1, "h": 60, "d": 1440}


def duration_minutes(value: Any) -> int:
    """Parse a duration into minutes; raises ``vol.Invalid``."""
    if isinstance(value, bool):
        raise vol.Invalid("invalid duration")
    if isinstance(value, (int, float)):
        minutes = int(value)
    else:
        match = re.fullmatch(r"(\d{1,5})\s*([mhd]?)", str(value).strip().lower())
        if not match:
            raise vol.Invalid(
                f"invalid duration '{value}' (minutes, or e.g. '30m', '3h', '1d')"
            )
        minutes = int(match[1]) * _UNITS[match[2]]
    if minutes < 1:
        raise vol.Invalid("a duration must be at least one minute")
    return minutes
