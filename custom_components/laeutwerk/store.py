"""Persistence of rules and reminder state (``.storage/laeutwerk``)."""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_MINOR_VERSION, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

SAVE_DELAY = 2  # seconds, debounced


class StoredData(TypedDict):
    """Top level storage layout."""

    rules: list[dict[str, Any]]
    # per rule id: reminders (open ones and recently finished ones)
    reminders: dict[str, list[dict[str, Any]]]
    # per rule id: finished reminders, newest first (added in 1.2)
    history: dict[str, list[dict[str, Any]]]
    # rule templates saved by the user (added in 1.3)
    templates: list[dict[str, Any]]


_REMOVED_TEXTS = (
    "title_plural",
    "message_plural",
    "text_plural",
    "headline_plural",
    "title_repeat",
    "message_repeat",
    "text_repeat",
)


def migrate_rule_0_11(rule: dict[str, Any]) -> dict[str, Any]:
    """Convert a rule to the 0.11 signal format (send_on, no plural/repeat texts)."""
    rule = {k: v for k, v in rule.items() if k not in _REMOVED_TEXTS}
    signals = []
    for old in rule.get("signals") or []:
        signal = {k: v for k, v in old.items() if k not in _REMOVED_TEXTS}
        every = signal.pop("every_stage", False)
        stage = int(signal.pop("stage", 0) or 0)
        once = (signal.get("limit") or {}).get("per_reminder") == 1
        if signal.get("when", "now") == "now":
            signal.pop("limit", None)
            if stage and not every:
                signal.update(send_on="stage", stage=stage, stage_repeat=not once)
            elif not stage and once and not every:
                signal["send_on"] = "first"
        elif stage:
            signal.update(send_on="stage", stage=stage)
        signals.append(signal)
    if "signals" in rule:
        rule["signals"] = signals
    return rule


class _VersionedStore(Store[StoredData]):
    """Store with a migration hook."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> StoredData:
        """Load an older store as is; missing parts start empty."""
        _LOGGER.debug(
            "Migrating storage from %s.%s", old_major_version, old_minor_version
        )
        convert = old_major_version == 1 and old_minor_version < 4
        rules = list(old_data.get("rules", []))
        templates = list(old_data.get("templates", []))
        if convert:
            rules = [migrate_rule_0_11(r) for r in rules]
            templates = [migrate_rule_0_11(t) for t in templates]
        return {
            "rules": rules,
            "reminders": dict(old_data.get("reminders", {})),
            "history": dict(old_data.get("history", {})),
            "templates": templates,
        }


class LaeutwerkStore:
    """Load and (debounced) save Läutwerk data."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise the store."""
        self._store = _VersionedStore(
            hass, STORAGE_VERSION, STORAGE_KEY, minor_version=STORAGE_MINOR_VERSION
        )

    async def async_load(self) -> StoredData:
        """Load stored data (empty layout when nothing is stored)."""
        data = await self._store.async_load()
        if not data:
            return {"rules": [], "reminders": {}, "history": {}, "templates": []}
        data.setdefault("rules", [])
        data.setdefault("reminders", {})
        data.setdefault("history", {})
        data.setdefault("templates", [])
        return data

    def async_schedule_save(self, data_func: Callable[[], StoredData]) -> None:
        """Save soon (debounced); also flushed on Home Assistant shutdown."""
        self._store.async_delay_save(data_func, SAVE_DELAY)

    async def async_save(self, data: StoredData) -> None:
        """Save immediately."""
        await self._store.async_save(data)
