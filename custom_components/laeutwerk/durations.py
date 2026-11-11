"""Durations as entered by users: minutes, or '30m' / '3h' / '1d'."""

from __future__ import annotations

from datetime import time, timedelta
import math
import re
from typing import Any

from homeassistant.util import dt as dt_util

from .compat import vol
from .timespec import local_instant

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


def minutes_until(when: time) -> int:
    """Minutes until the next time this local time of day is reached (>= 1)."""
    tz = dt_util.get_default_time_zone()
    now = dt_util.utcnow()
    local = now.astimezone(tz)
    minute = when.hour * 60 + when.minute
    target = local_instant(local.date(), minute, tz)
    if target <= now:
        target = local_instant(local.date() + timedelta(days=1), minute, tz)
    return max(1, math.ceil((target - now).total_seconds() / 60))
