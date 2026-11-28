"""Variables supplied by other integrations (see docs/VARIABLE_PROVIDERS.md)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant

from .matching import template_variables

_LOGGER = logging.getLogger(__name__)

PROVIDERS_KEY = "laeutwerk_variable_providers"
EVENT_PROVIDERS_CHANGED = "laeutwerk_variable_providers_changed"
PROVIDER_TIMEOUT = 2
_WARN_EVERY = 60.0
_last_warned: dict[str, float] = {}


def _warn(key: str, text: str, *args: Any) -> None:
    now = time.monotonic()
    if now - _last_warned.get(key, -_WARN_EVERY) >= _WARN_EVERY:
        _last_warned[key] = now
        _LOGGER.warning(text, *args)


def _names_of(provider: Any) -> set[str]:
    return {
        str(v["name"])
        for v in provider.variables()
        if isinstance(v, Mapping) and v.get("name")
    }


def provider_catalog(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return registered providers with their variables (broken ones skipped)."""
    catalog: list[dict[str, Any]] = []
    for key, provider in list(hass.data.get(PROVIDERS_KEY, {}).items()):
        try:
            variables = [
                {
                    "name": str(v["name"]),
                    "description": str(v.get("description", "")),
                    "example": str(v.get("example", "")),
                }
                for v in provider.variables()
                if isinstance(v, Mapping) and v.get("name")
            ]
            catalog.append(
                {"key": str(key), "title": str(provider.title), "variables": variables}
            )
        except Exception as err:
            _warn(f"cat:{key}", "Variable provider %s is broken: %s", key, err)
    return catalog


async def async_provider_values(
    hass: HomeAssistant,
    texts: Iterable[str | None],
    base_vars: Mapping[str, str],
    context: Mapping[str, Any],
) -> dict[str, str]:
    """Values from providers for the placeholders in ``texts`` not in base_vars."""
    providers = hass.data.get(PROVIDERS_KEY)
    if not providers:
        return {}
    wanted: set[str] = set()
    for text in texts:
        wanted |= template_variables(text)
    wanted -= set(base_vars)
    if not wanted:
        return {}
    ctx = {**context, "variables": dict(base_vars)}
    values: dict[str, str] = {}
    for key, provider in list(providers.items()):
        try:
            names = (_names_of(provider) & wanted) - set(values)
            if not names:
                continue
            async with asyncio.timeout(PROVIDER_TIMEOUT):
                got = await provider.async_values(set(names), dict(ctx))
            for name, value in (got or {}).items():
                if name in names and value is not None:
                    values[name] = str(value)
        except Exception as err:
            _warn(f"val:{key}", "Variable provider %s failed: %r", key, err)
    return values


def config_texts(value: Any) -> list[str]:
    """All strings inside a (nested) signal configuration."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [t for v in value.values() for t in config_texts(v)]
    if isinstance(value, (list, tuple)):
        return [t for v in value for t in config_texts(v)]
    return []


class PassDraw:
    """Provider values of one reminder pass, drawn once for all its signals."""

    def __init__(self, kind: str, signals: list[Any]) -> None:
        """Remember the pass kind and the signals sent in it."""
        self.kind = kind
        self.signals = signals
        self._lock = asyncio.Lock()
        self._values: dict[str, str] | None = None

    async def async_values(
        self,
        hass: HomeAssistant,
        rule: Any,
        base_vars: Mapping[str, str],
    ) -> dict[str, str]:
        """Draw on first call, then return the same values."""
        async with self._lock:
            if self._values is None:
                single = self.signals[0] if len(self.signals) == 1 else None
                self._values = await async_provider_values(
                    hass,
                    [t for s in self.signals for t in config_texts(s.config)],
                    base_vars,
                    provider_context(hass, rule, single, self.kind, base_vars),
                )
            return self._values


def provider_context(
    hass: HomeAssistant,
    rule: Any,
    signal: Any,
    kind: str,
    base_vars: Mapping[str, str],
) -> dict[str, Any]:
    """Context dict handed to providers."""
    return {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "signal_id": signal.id if signal else None,
        "signal_type": signal.type if signal else None,
        "pass_kind": kind,
        "language": hass.config.language,
        "variables": dict(base_vars),
    }
