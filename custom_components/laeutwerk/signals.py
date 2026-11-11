"""Send the signals of a rule: push, light, announcement, custom action.

Also the per-signal limits that decide *whether* a signal may be sent now:
conditions ("only if"), quiet times and frequency.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time, timedelta, tzinfo
import logging
from typing import Any

from homeassistant.core import Context, HomeAssistant, State
from homeassistant.exceptions import ConditionError, HomeAssistantError
from homeassistant.helpers import (
    condition as condition_helper,
    config_validation as cv,
    entity_registry as er,
    script as script_helper,
)
from homeassistant.util import slugify

from .colors import parse_color
from .compat import vol
from .const import (
    ACTION_ACK_PREFIX,
    ACTION_SNOOZE_PREFIX,
    DOMAIN,
    NOTIFICATION_TAG_PREFIX,
)
from .durations import duration_minutes
from .matching import render
from .model import (
    AUDIENCE_ALL,
    AUDIENCE_ASSIGNEE,
    AUDIENCE_PERSONS,
    AUDIENCE_PRESENT,
    EFFECT_PULSE,
    MATCH_ANY,
    QUIET_DEFER,
    SIGNAL_ACTION,
    SIGNAL_ANNOUNCE,
    SIGNAL_LIGHT,
    SIGNAL_NOTIFY,
    Reminder,
    Signal,
)
from .timespec import local_instant

_LOGGER = logging.getLogger(__name__)

MOBILE_APP_PREFIX = "notify.mobile_app_"
CLEAR_NOTIFICATION = "clear_notification"
COLOR_MODES = ("hs", "rgb", "xy", "rgbw", "rgbww")
PULSE_LOW_PCT = 8

# One light signal per lamp at a time (the saved state must be the real one).
_LIGHT_LOCKS: dict[str, asyncio.Lock] = {}


@dataclass(slots=True)
class SignalRun:
    """Everything needed to send one signal for one reminder."""

    hass: HomeAssistant
    rule_name: str
    signal: Signal
    reminder_id: str
    variables: Mapping[str, str]
    plural: bool
    context: Context
    # Responsible person (entity id) for audience "assignee".
    assignee: str | None = None

    def text(self, key: str) -> str:
        """Render a text field, using its plural variant if it applies."""
        config = self.signal.config
        template = (self.plural and config.get(f"{key}_plural")) or config.get(key)
        return render(template, self.variables)


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def _async_call(
    hass: HomeAssistant,
    domain: str,
    service: str,
    data: dict[str, Any],
    context: Context,
) -> bool:
    """Call an action; log instead of raising."""
    if not hass.services.has_service(domain, service):
        _LOGGER.warning("Action %s.%s does not exist", domain, service)
        return False
    try:
        await hass.services.async_call(
            domain, service, data, blocking=True, context=context
        )
    except (HomeAssistantError, vol.Invalid) as err:
        _LOGGER.warning("Action %s.%s failed: %s", domain, service, err)
        return False
    return True


# --------------------------------------------------------------------- limits


def _parse_time(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def quiet_until(
    signal: Signal, now: datetime, tz: tzinfo
) -> tuple[str, datetime] | None:
    """Return (mode, end as UTC) of the quiet time that covers ``now``."""
    local = now.astimezone(tz)
    current = local.time().replace(second=0, microsecond=0)
    for window in signal.config.get("quiet", []):
        start, end = _parse_time(window["from"]), _parse_time(window["to"])
        if start == end:
            continue
        end_minute = end.hour * 60 + end.minute
        if start < end:
            if start <= current < end:
                return window["mode"], local_instant(local.date(), end_minute, tz)
        elif current >= start:
            day = local.date() + timedelta(days=1)
            return window["mode"], local_instant(day, end_minute, tz)
        elif current < end:
            return window["mode"], local_instant(local.date(), end_minute, tz)
    return None


def limit_reached(signal: Signal, reminder: Reminder, now: datetime) -> bool:
    """Whether the frequency limit forbids sending the signal now."""
    limit = signal.config.get("limit") or {}
    maximum = limit.get("per_reminder")
    if maximum and reminder.signals_sent.get(signal.id, 0) >= maximum:
        return True
    interval = limit.get("min_interval")
    last = reminder.signal_last.get(signal.id)
    return bool(interval and last and now < last + timedelta(minutes=interval))


async def async_conditions_met(hass: HomeAssistant, signal: Signal) -> bool:
    """Evaluate the "only if" conditions of a signal (all / any)."""
    conditions = signal.config.get("conditions")
    if not conditions:
        return True
    results: list[bool] = []
    try:
        validated = await condition_helper.async_validate_conditions_config(
            hass, cv.CONDITIONS_SCHEMA(conditions)
        )
        for config in validated:
            checker = await condition_helper.async_from_config(hass, config)
            results.append(checker(hass) is True)
    except (vol.Invalid, ConditionError, HomeAssistantError) as err:
        _LOGGER.warning("Signal %s: condition error: %s", signal.id, err)
        return False
    if signal.config.get("conditions_match") == MATCH_ANY:
        return any(results)
    return all(results)


def is_deferrable(mode: str) -> bool:
    """Whether a signal skipped by a quiet time is sent when it ends."""
    return mode == QUIET_DEFER


# ----------------------------------------------------------------------- push


def notification_tag(reminder_id: str) -> str:
    """Tag that lets a later notification replace or clear this one."""
    return f"{NOTIFICATION_TAG_PREFIX}{reminder_id}"


def person_notify_targets(hass: HomeAssistant, person: State) -> list[str]:
    """Notify actions of the mobile app devices of a person."""
    registry = er.async_get(hass)
    targets: list[str] = []
    for tracker in person.attributes.get("device_trackers", []):
        entry = registry.async_get(tracker)
        if entry is None or entry.platform != "mobile_app":
            continue
        config_entry = hass.config_entries.async_get_entry(entry.config_entry_id or "")
        if config_entry is None:
            continue
        name = config_entry.data.get("device_name") or config_entry.title
        target = f"{MOBILE_APP_PREFIX}{slugify(name)}"
        if target not in targets:
            targets.append(target)
    return targets


def notify_targets(
    hass: HomeAssistant, signal: Signal, assignee: str | None = None
) -> list[str]:
    """Resolve the audience and explicit targets of a push signal."""
    config = signal.config
    targets: list[str] = list(config.get("targets", []))
    audience = config.get("audience")
    persons: list[State] = []
    if audience in (AUDIENCE_ALL, AUDIENCE_PRESENT):
        persons = [
            state
            for state in hass.states.async_all("person")
            if audience == AUDIENCE_ALL or state.state == "home"
        ]
    elif audience == AUDIENCE_ASSIGNEE:
        persons = [state] if assignee and (state := hass.states.get(assignee)) else []
    elif audience == AUDIENCE_PERSONS:
        persons = [
            state
            for entity_id in config.get("persons", [])
            if (state := hass.states.get(entity_id)) is not None
            and (not config.get("only_present") or state.state == "home")
        ]
    for person in persons:
        for target in person_notify_targets(hass, person):
            if target not in targets:
                targets.append(target)
    return targets


def notify_payload(run: SignalRun) -> dict[str, Any]:
    """Service data for a notify action (title, message, buttons)."""
    config = run.signal.config
    data: dict[str, Any] = {
        **config.get("data", {}),
        "tag": notification_tag(run.reminder_id),
    }
    buttons = []
    for action in config.get("actions", []):
        if action.get("ack"):
            action_id = f"{ACTION_ACK_PREFIX}{run.reminder_id}"
        else:
            minutes = duration_minutes(action["snooze"])
            action_id = f"{ACTION_SNOOZE_PREFIX}{minutes}__{run.reminder_id}"
        buttons.append({"action": action_id, "title": action["label"]})
    if buttons:
        data["actions"] = buttons
    payload: dict[str, Any] = {"message": run.text("message"), "data": data}
    if title := run.text("title"):
        payload["title"] = title
    return payload


async def _async_notify(run: SignalRun) -> bool:
    payload = notify_payload(run)
    sent = False
    for target in notify_targets(run.hass, run.signal, run.assignee):
        domain, _, service = target.partition(".")
        sent = (
            await _async_call(run.hass, domain, service, payload, run.context) or sent
        )
    return sent


async def async_clear_notifications(
    hass: HomeAssistant, signals: list[Signal], reminder: Reminder, context: Context
) -> None:
    """Remove the push notifications of a reminder from the phones."""
    payload = {
        "message": CLEAR_NOTIFICATION,
        "data": {"tag": notification_tag(reminder.id)},
    }
    for signal in signals:
        if signal.type != SIGNAL_NOTIFY or not reminder.signals_sent.get(signal.id):
            continue
        for target in notify_targets(hass, signal, reminder.assignee):
            if target.startswith(MOBILE_APP_PREFIX):
                domain, _, service = target.partition(".")
                await _async_call(hass, domain, service, payload, context)


# ---------------------------------------------------------------------- light


def light_snapshot(state: State) -> dict[str, Any]:
    """Return what is needed to bring a light back to its current state."""
    if state.state != "on":
        return {"on": False}
    attributes = state.attributes
    data: dict[str, Any] = {}
    if attributes.get("brightness") is not None:
        data["brightness"] = attributes["brightness"]
    mode = attributes.get("color_mode")
    if mode == "color_temp" and attributes.get("color_temp_kelvin"):
        data["color_temp_kelvin"] = attributes["color_temp_kelvin"]
    elif mode in COLOR_MODES and attributes.get(f"{mode}_color") is not None:
        data[f"{mode}_color"] = list(attributes[f"{mode}_color"])
    return {"on": True, "data": data}


def light_color(run: SignalRun) -> tuple[int, int, int] | None:
    """Colour of a light signal: from a keyword column or fixed."""
    config = run.signal.config
    column = config.get("color_from")
    from_column = parse_color(run.variables.get(column)) if column else None
    return from_column or parse_color(config.get("color"))


async def _async_light_one(
    run: SignalRun, entity_id: str, rgb: tuple[int, int, int] | None
) -> bool:
    hass, config = run.hass, run.signal.config
    lock = _LIGHT_LOCKS.setdefault(entity_id, asyncio.Lock())
    if lock.locked():
        return False
    async with lock:
        state = hass.states.get(entity_id)
        if state is None or state.state not in ("on", "off"):
            _LOGGER.warning("Light %s is not available for a signal", entity_id)
            return False
        saved = light_snapshot(state)
        pattern = config.get("pattern") or {}
        pulse = pattern.get("effect") == EFFECT_PULSE
        interval = float(pattern.get("interval", 0.8))
        transition = interval if pulse else 0
        on_data: dict[str, Any] = {
            "entity_id": entity_id,
            "brightness_pct": config.get("brightness", 100),
            "transition": transition,
        }
        modes = state.attributes.get("supported_color_modes") or []
        if rgb and any(mode in COLOR_MODES for mode in modes):
            on_data["rgb_color"] = list(rgb)

        async def light(service: str, data: dict[str, Any]) -> bool:
            return await _async_call(hass, "light", service, data, run.context)

        ok = True
        for _ in range(int(pattern.get("count", 3))):
            ok = await light("turn_on", on_data) and ok
            await _sleep(interval)
            if pulse:
                low = {**on_data, "brightness_pct": PULSE_LOW_PCT}
                ok = await light("turn_on", low) and ok
            else:
                ok = await light("turn_off", {"entity_id": entity_id}) and ok
            await _sleep(interval)
        if not config.get("restore", True):
            await light("turn_on", on_data)
        elif saved["on"]:
            await light(
                "turn_on", {"entity_id": entity_id, "transition": 0, **saved["data"]}
            )
        else:
            await light("turn_off", {"entity_id": entity_id, "transition": 0})
        return ok


async def _async_light(run: SignalRun) -> bool:
    rgb = light_color(run)
    results = await asyncio.gather(
        *(
            _async_light_one(run, entity_id, rgb)
            for entity_id in run.signal.config.get("entities", [])
        )
    )
    return any(results)


# --------------------------------------------------------------- announcement


def _media_source_id(hass: HomeAssistant, message: str, **kwargs: Any) -> str:
    """TTS media source id (imported lazily: tts is an optional dependency)."""
    from homeassistant.components.tts import (  # noqa: PLC0415
        generate_media_source_id,
    )

    return generate_media_source_id(hass, message, **kwargs)


async def _async_announce(run: SignalRun) -> bool:
    hass, config = run.hass, run.signal.config
    message = run.text("text")
    engine = config.get("tts") or next(iter(hass.states.async_entity_ids("tts")), None)
    options = {"voice": config["voice"]} if config.get("voice") else None
    try:
        media_id = _media_source_id(
            hass,
            message,
            engine=engine,
            language=config.get("language"),
            options=options,
        )
    except (HomeAssistantError, KeyError, ImportError) as err:
        _LOGGER.warning("Announcement of signal %s failed: %s", run.signal.id, err)
        return False
    data: dict[str, Any] = {
        "entity_id": list(config.get("players", [])),
        "media_content_id": media_id,
        "media_content_type": "music",
        "announce": True,
    }
    if config.get("volume") is not None:
        # Announcement volume, used by players that support it (e.g. Sonos).
        data["extra"] = {"volume": config["volume"]}
    return await _async_call(hass, "media_player", "play_media", data, run.context)


# -------------------------------------------------------------- custom action


async def _async_action(run: SignalRun) -> bool:
    hass = run.hass
    try:
        sequence = await script_helper.async_validate_actions_config(
            hass, cv.SCRIPT_SCHEMA(run.signal.config.get("actions", []))
        )
        script = script_helper.Script(
            hass,
            sequence,
            f"{run.rule_name}: {run.signal.id}",
            DOMAIN,
            script_mode=script_helper.SCRIPT_MODE_PARALLEL,
            logger=_LOGGER,
        )
        variables = {
            **run.variables,
            "reminder_id": run.reminder_id,
            "plural": run.plural,
        }
        await script.async_run(run_variables=variables, context=run.context)
    except (vol.Invalid, HomeAssistantError) as err:
        _LOGGER.warning("Action of signal %s failed: %s", run.signal.id, err)
        return False
    return True


_SENDERS = {
    SIGNAL_NOTIFY: _async_notify,
    SIGNAL_LIGHT: _async_light,
    SIGNAL_ANNOUNCE: _async_announce,
    SIGNAL_ACTION: _async_action,
}


async def async_send_signal(run: SignalRun) -> bool:
    """Send one signal; True if it reached at least one target."""
    sender = _SENDERS.get(run.signal.type)
    if sender is None:
        return False
    try:
        return await sender(run)
    except Exception:
        _LOGGER.exception("Signal %s failed unexpectedly", run.signal.id)
        return False
