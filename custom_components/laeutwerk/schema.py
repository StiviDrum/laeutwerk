"""Validation of rules (structure and meaning) with helpful messages."""

from __future__ import annotations

from datetime import date
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    condition as condition_helper,
    config_validation as cv,
    script as script_helper,
)
from homeassistant.util import slugify

from .compat import vol
from .durations import duration_minutes
from .matching import EVENT_VARIABLES
from .model import (
    ACK_NOTIFY_ACTION,
    ACK_TAG,
    ACK_TRIGGER,
    AUDIENCE_ASSIGNEE,
    AUDIENCE_PERSONS,
    AUDIENCES,
    DEFAULT_EXPIRE,
    DEFAULT_REPEAT_MAX,
    EFFECT_BLINK,
    EFFECTS,
    MATCH_ALL,
    MATCH_ANY,
    MATCH_CONTAINS,
    MATCH_MODES,
    MATCH_REGEX,
    QUIET_MODES,
    QUIET_SKIP,
    REPEAT_NONE,
    ROTATION_FIXED,
    ROTATIONS,
    SIGNAL_ACTION,
    SIGNAL_ANNOUNCE,
    SIGNAL_LIGHT,
    SIGNAL_NOTIFY,
    SIGNAL_TYPES,
    WHEN_NOW,
)
from .sources import SOURCE_DOMAINS
from .timespec import KIND_EVENT_END, KIND_EVENT_START, parse_timespec
from .triggers import as_trigger_list, async_validate_triggers

_COLUMN = re.compile(r"^[^\W\d][\w]*$")
_ROW_KEYS = ("match", "mode")
_UMLAUTS = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"}
)


def _text(value: Any) -> str:
    return cv.string(value).strip()


def _non_empty(value: Any) -> str:
    text = _text(value)
    if not text:
        raise vol.Invalid("must not be empty")
    return text


def _reminder_time(value: Any) -> str:
    text = _non_empty(value)
    try:
        spec = parse_timespec(text)
    except ValueError as err:
        raise vol.Invalid(str(err)) from err
    if spec.kind in (KIND_EVENT_START, KIND_EVENT_END):
        raise vol.Invalid(f"'{text}' is only allowed for 'expire'")
    return text


def _expire_time(value: Any) -> str:
    text = _non_empty(value)
    try:
        parse_timespec(text)
    except ValueError as err:
        raise vol.Invalid(str(err)) from err
    return text


def _source_entity(value: Any) -> str:
    entity_id = cv.entity_id(value)
    if entity_id.split(".", 1)[0] not in SOURCE_DOMAINS:
        raise vol.Invalid(
            f"'{entity_id}' cannot be a source (allowed: "
            f"{', '.join(d + '.*' for d in SOURCE_DOMAINS)})"
        )
    return entity_id


def duration_days(value: Any) -> int:
    """Parse a number of days: 90, '90d', '12w'."""
    if isinstance(value, bool):
        raise vol.Invalid("invalid number of days")
    if isinstance(value, int):
        days = value
    else:
        match = re.fullmatch(r"(\d{1,4})\s*([dw]?)", _text(value).lower())
        if not match:
            raise vol.Invalid(f"invalid interval '{value}' (e.g. 90, '90d', '12w')")
        days = int(match[1]) * (7 if match[2] == "w" else 1)
    if days < 1:
        raise vol.Invalid("an interval must be at least one day")
    return days


def _month_day(value: Any) -> str:
    text = _non_empty(value)
    match = re.fullmatch(r"(\d{1,2})-(\d{1,2})", text)
    if not match:
        raise vol.Invalid(f"'{value}' is not a month-day (MM-DD, e.g. '04-01')")
    month, day = int(match[1]), int(match[2])
    try:
        date(2024, month, day)  # leap year: 02-29 is allowed
    except ValueError as err:
        raise vol.Invalid(f"'{value}' is not a valid day of the year") from err
    return f"{month:02d}-{day:02d}"


def _escalation_after(value: Any) -> str:
    text = _non_empty(value).lower()
    if re.fullmatch(r"\d{1,2}:\d{2}", text):
        return _clock(text)
    try:
        duration_minutes(text.lstrip("+"))
    except vol.Invalid as err:
        raise vol.Invalid(
            f"invalid escalation time '{value}' (after a duration such as '2h', "
            "'30m' or at a time of day such as '21:30')"
        ) from err
    return text.lstrip("+")


def _notify_target(value: Any) -> str:
    target = _non_empty(value).lower()
    if not re.fullmatch(r"notify\.[a-z0-9_]+", target):
        raise vol.Invalid(
            f"'{value}' is not a notify action (e.g. 'notify.mobile_app_phone')"
        )
    return target


def _column(value: Any) -> str:
    name = _non_empty(value).lower()
    if not _COLUMN.fullmatch(name):
        raise vol.Invalid(
            f"column '{value}' must be a single word of letters, digits and '_'"
        )
    return name


def _keywords(value: Any) -> dict[str, Any]:
    """Validate the keyword table: columns and flat rows."""
    data = vol.Schema(
        {
            vol.Optional("columns", default=list): [_column],
            vol.Optional("rows", default=list): [dict],
        }
    )(value or {})
    columns: list[str] = data["columns"]
    if len(set(columns)) != len(columns):
        raise vol.Invalid("column names must be unique")
    taken = set(EVENT_VARIABLES) | set(_ROW_KEYS) | set(columns)
    for column in columns:
        if column in EVENT_VARIABLES or column in _ROW_KEYS:
            raise vol.Invalid(f"column name '{column}' is reserved")
        if f"{column}n" in taken:
            raise vol.Invalid(
                f"column '{column}': its plural variable '{column}n' clashes "
                "with another variable"
            )
    rows = []
    for index, raw in enumerate(data["rows"], start=1):
        row = {str(key).lower(): val for key, val in raw.items()}
        if unknown := set(row) - set(columns) - set(_ROW_KEYS):
            raise vol.Invalid(
                f"keyword row {index}: unknown column(s) {', '.join(sorted(unknown))}"
            )
        try:
            match = _non_empty(row.get("match", ""))
        except vol.Invalid as err:
            raise vol.Invalid(f"keyword row {index}: 'match' {err}") from err
        mode = row.get("mode", MATCH_CONTAINS)
        if mode not in MATCH_MODES:
            raise vol.Invalid(
                f"keyword row {index}: mode must be one of {', '.join(MATCH_MODES)}"
            )
        if mode == MATCH_REGEX:
            try:
                re.compile(match)
            except re.error as err:
                raise vol.Invalid(
                    f"keyword row {index}: invalid regular expression ({err})"
                ) from err
        clean: dict[str, Any] = {"match": match}
        if mode != MATCH_CONTAINS:
            clean["mode"] = mode
        for column in columns:
            clean[column] = _text(row.get(column, "") or "")
        rows.append(clean)
    return {"columns": columns, "rows": rows}


_FILTER_SCHEMA = vol.Schema(
    {
        vol.Optional("all_day", default=False): cv.boolean,
        vol.Optional("keywords", default=dict): _keywords,
    }
)


def _snooze(value: Any) -> Any:
    duration_minutes(value)
    return value


_NOTIFY_ACTION_SCHEMA = vol.Any(
    vol.Schema({vol.Required("ack"): True, vol.Required("label"): _non_empty}),
    vol.Schema({vol.Required("snooze"): _snooze, vol.Required("label"): _non_empty}),
    msg="a push button needs a 'label' and either 'ack: true' or 'snooze: <duration>'",
)


def _clock(value: Any) -> str:
    text = _non_empty(value)
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not match or int(match[1]) > 23 or int(match[2]) > 59:
        raise vol.Invalid(f"'{value}' is not a time of day (HH:MM)")
    return f"{int(match[1]):02d}:{match[2]}"


def _domain_entity(domain: str) -> Any:
    def validate(value: Any) -> str:
        entity_id = cv.entity_id(value)
        if not entity_id.startswith(f"{domain}."):
            raise vol.Invalid(f"'{entity_id}' is not a {domain} entity")
        return entity_id

    return validate


def _conditions(value: Any) -> list[dict[str, Any]]:
    """Check conditions but keep them as given (the editor needs the raw form)."""
    conditions = cv.ensure_list(value)
    cv.CONDITIONS_SCHEMA(conditions)
    return conditions


def _conditions_or_empty(value: Any) -> list[dict[str, Any]]:
    return _conditions(value) if value else []


def _actions_or_empty(value: Any) -> list[dict[str, Any]]:
    return _actions(value) if value else []


def _actions(value: Any) -> list[dict[str, Any]]:
    """Check a Home Assistant action sequence but keep it as given."""
    actions = cv.ensure_list(value)
    if not actions:
        raise vol.Invalid("at least one action is required")
    cv.SCRIPT_SCHEMA(actions)
    return actions


_QUIET_SCHEMA = vol.Schema(
    {
        vol.Required("from"): _clock,
        vol.Required("to"): _clock,
        vol.Optional("mode", default=QUIET_SKIP): vol.In(QUIET_MODES),
    }
)

_LIMIT_SCHEMA = vol.Schema(
    {
        # How often per reminder at most.
        vol.Optional("per_reminder"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        # Minimum minutes between two sends.
        vol.Optional("min_interval"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)

_SIGNAL_BASE = {
    vol.Optional("id"): cv.slug,
    vol.Required("type"): vol.In(SIGNAL_TYPES),
    vol.Optional("enabled", default=True): cv.boolean,
    vol.Optional("when", default=WHEN_NOW): vol.Any(
        WHEN_NOW,
        vol.Schema(
            {
                # Any Home Assistant trigger(s), as in automations.
                vol.Required("opportunity"): as_trigger_list,
                # Only real operation counts (context without a parent).
                vol.Optional("manual_only", default=False): cv.boolean,
            }
        ),
        msg="'when' must be 'now' or an object with 'opportunity' (triggers)",
    ),
    vol.Optional("conditions"): _conditions,
    vol.Optional("conditions_match", default=MATCH_ALL): vol.In([MATCH_ALL, MATCH_ANY]),
    vol.Optional("limit"): _LIMIT_SCHEMA,
    vol.Optional("quiet"): [_QUIET_SCHEMA],
    # Escalation stage from which the signal is active (0 = from the start).
    vol.Optional("stage"): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
}

_SIGNAL_SCHEMAS = {
    SIGNAL_NOTIFY: vol.Schema(
        {
            **_SIGNAL_BASE,
            vol.Optional("targets"): vol.All(cv.ensure_list, [_notify_target]),
            vol.Optional("audience"): vol.In(AUDIENCES),
            vol.Optional("persons"): vol.All(
                cv.ensure_list, [_domain_entity("person")]
            ),
            vol.Optional("title"): _text,
            vol.Optional("title_plural"): _text,
            vol.Required("message"): _non_empty,
            vol.Optional("message_plural"): _text,
            vol.Optional("actions", default=list): [_NOTIFY_ACTION_SCHEMA],
            vol.Optional("data"): dict,
        }
    ),
    SIGNAL_LIGHT: vol.Schema(
        {
            **_SIGNAL_BASE,
            vol.Required("entities"): vol.All(
                cv.ensure_list, [_domain_entity("light")], vol.Length(min=1)
            ),
            vol.Optional("pattern", default=dict): vol.Schema(
                {
                    vol.Optional("effect", default=EFFECT_BLINK): vol.In(EFFECTS),
                    vol.Optional("count", default=3): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=20)
                    ),
                    # Seconds per half period (on, then off / dimmed).
                    vol.Optional("interval", default=0.8): vol.All(
                        vol.Coerce(float), vol.Range(min=0.2, max=5)
                    ),
                }
            ),
            vol.Optional("color"): _text,
            vol.Optional("color_from"): _column,
            vol.Optional("brightness", default=100): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=100)
            ),
            vol.Optional("restore", default=True): cv.boolean,
        }
    ),
    SIGNAL_ANNOUNCE: vol.Schema(
        {
            **_SIGNAL_BASE,
            vol.Required("players"): vol.All(
                cv.ensure_list, [_domain_entity("media_player")], vol.Length(min=1)
            ),
            vol.Required("text"): _non_empty,
            vol.Optional("text_plural"): _text,
            vol.Optional("volume"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            vol.Optional("tts"): _domain_entity("tts"),
            vol.Optional("language"): _text,
            vol.Optional("voice"): _text,
        }
    ),
    SIGNAL_ACTION: vol.Schema({**_SIGNAL_BASE, vol.Required("actions"): _actions}),
}


def validate_signal(value: Any) -> dict[str, Any]:
    """Validate one signal (also used for testing an unsaved signal)."""
    if not isinstance(value, dict):
        raise vol.Invalid("a signal must be an object")
    signal_type = value.get("type")
    if signal_type not in _SIGNAL_SCHEMAS:
        raise vol.Invalid(
            f"unknown signal type '{signal_type}' "
            f"(supported: {', '.join(_SIGNAL_SCHEMAS)})"
        )
    value = dict(value)
    if signal_type == SIGNAL_LIGHT and "entity" in value:
        # Short form of the specification: a single lamp as "entity".
        value.setdefault("entities", value.pop("entity"))
    signal: dict[str, Any] = _SIGNAL_SCHEMAS[signal_type](value)
    if signal_type == SIGNAL_NOTIFY:
        audience = signal.get("audience")
        if not signal.get("targets") and not audience:
            raise vol.Invalid("a push signal needs 'targets' or an 'audience'")
        if audience == AUDIENCE_PERSONS and not signal.get("persons"):
            raise vol.Invalid("audience 'persons' needs a list of 'persons'")
    return signal


def _signals(value: Any) -> list[dict[str, Any]]:
    """Validate signals and give each a unique id."""
    signals = [validate_signal(item) for item in cv.ensure_list(value)]
    used = {signal["id"] for signal in signals if "id" in signal}
    if len(used) != sum(1 for signal in signals if "id" in signal):
        raise vol.Invalid("signal ids must be unique")
    for signal in signals:
        if "id" not in signal:
            candidate, counter = signal["type"], 2
            while candidate in used:
                candidate = f"{signal['type']}_{counter}"
                counter += 1
            signal["id"] = candidate
            used.add(candidate)
    return signals


_ACK_SCHEMAS = {
    ACK_NOTIFY_ACTION: vol.Schema({vol.Required("type"): ACK_NOTIFY_ACTION}),
    ACK_TAG: vol.Schema(
        {
            vol.Required("type"): ACK_TAG,
            vol.Required("tag_id"): _non_empty,
            vol.Optional("name"): _text,
        }
    ),
    # Door contact, zone, button ...: any Home Assistant trigger.
    ACK_TRIGGER: vol.Schema(
        {
            vol.Required("type"): ACK_TRIGGER,
            vol.Required("trigger"): as_trigger_list,
            vol.Optional("name"): _text,
            # Also before the reminder time (like the tag and the button).
            vol.Optional("early", default=False): cv.boolean,
        }
    ),
}


def _ack(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("type") not in _ACK_SCHEMAS:
        raise vol.Invalid(f"acknowledge type must be one of {', '.join(_ACK_SCHEMAS)}")
    result: dict[str, Any] = _ACK_SCHEMAS[value["type"]](value)
    return result


_REPEAT_SCHEMA = vol.Any(
    REPEAT_NONE,
    vol.Schema(
        {
            # Minutes between repetitions while the reminder is open.
            vol.Required("every"): duration_minutes,
            vol.Optional("max", default=DEFAULT_REPEAT_MAX): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=1000)
            ),
        }
    ),
    msg="'repeat' must be 'none' or an object with 'every' (and 'max')",
)

_INTERVAL_SCHEMA = vol.Schema(
    {
        vol.Required("every"): duration_days,
        # First due day while it was never done (default: the day it is saved).
        vol.Optional("start"): vol.All(cv.date, lambda day: day.isoformat()),
    }
)

_ACTIVATION_SCHEMA = vol.Schema(
    {
        vol.Optional("conditions", default=list): _conditions_or_empty,
        vol.Optional("match", default=MATCH_ALL): vol.In([MATCH_ALL, MATCH_ANY]),
        vol.Optional("season"): vol.Schema(
            {vol.Required("from"): _month_day, vol.Required("to"): _month_day}
        ),
    }
)

_ASSIGNEE_SCHEMA = vol.Schema(
    {
        vol.Required("persons"): vol.All(
            cv.ensure_list, [_domain_entity("person")], vol.Length(min=1), vol.Unique()
        ),
        vol.Optional("rotation", default=ROTATION_FIXED): vol.In(ROTATIONS),
    }
)

RULE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.slug,
        vol.Required("name"): _non_empty,
        vol.Optional("icon", default=None): vol.Any(None, cv.icon),
        vol.Optional("color", default=None): vol.Any(None, _text),
        vol.Optional("enabled", default=True): cv.boolean,
        vol.Optional("sources", default=list): vol.All(
            cv.ensure_list, [_source_entity], vol.Unique()
        ),
        vol.Optional("filter", default=dict): _FILTER_SCHEMA,
        vol.Required("reminders"): vol.All(
            cv.ensure_list,
            [vol.Schema({vol.Required("at"): _reminder_time})],
            vol.Length(min=1),
        ),
        vol.Optional("signals", default=list): _signals,
        vol.Optional("acknowledge", default=list): [_ack],
        vol.Optional("ack_label", default=None): vol.Any(None, _text),
        vol.Optional("repeat", default=REPEAT_NONE): _REPEAT_SCHEMA,
        vol.Optional("bundle", default=True): cv.boolean,
        vol.Optional("expire", default=DEFAULT_EXPIRE): _expire_time,
        vol.Optional("interval", default=None): vol.Any(None, _INTERVAL_SCHEMA),
        vol.Optional("activation", default=None): vol.Any(None, _ACTIVATION_SCHEMA),
        vol.Optional("on_done", default=list): _actions_or_empty,
        vol.Optional("assignee", default=None): vol.Any(None, _ASSIGNEE_SCHEMA),
        vol.Optional("escalation", default=list): [
            vol.Schema({vol.Required("after"): _escalation_after})
        ],
    }
)


def validate_rule(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a rule; raises ``vol.Invalid`` with a readable message."""
    rule: dict[str, Any] = RULE_SCHEMA(data)
    columns = rule["filter"]["keywords"]["columns"]
    for signal in rule["signals"]:
        column = signal.get("color_from")
        if column and column not in columns:
            raise vol.Invalid(
                f"signal '{signal['id']}': color_from '{column}' is not a column "
                "of the keyword table"
            )
    if not rule["sources"] and not rule["interval"]:
        raise vol.Invalid("a rule needs at least one source or an 'interval'")
    stages = len(rule["escalation"])
    for signal in rule["signals"]:
        if signal.get("stage", 0) > stages:
            raise vol.Invalid(
                f"signal '{signal['id']}': stage {signal['stage']} does not exist "
                f"(the rule has {stages} escalation stage(s))"
            )
        if signal.get("audience") == AUDIENCE_ASSIGNEE and not rule["assignee"]:
            raise vol.Invalid(
                f"signal '{signal['id']}': audience 'assignee' needs 'assignee' "
                "(responsible persons) in the rule"
            )
    ats = [item["at"] for item in rule["reminders"]]
    if len(set(ats)) != len(ats):
        raise vol.Invalid("reminder times must be unique")
    return rule


async def async_validate_rule(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate a rule incl. its conditions and actions against Home Assistant.

    Conditions and actions of other integrations can only be checked while
    Home Assistant is running, so this is used when a rule is created or
    changed; stored rules are loaded with ``validate_rule``.
    """
    rule = validate_rule(data)
    for signal in rule["signals"]:
        try:
            if conditions := signal.get("conditions"):
                await condition_helper.async_validate_conditions_config(
                    hass, cv.CONDITIONS_SCHEMA(conditions)
                )
            if isinstance(signal["when"], dict):
                await async_validate_triggers(hass, signal["when"]["opportunity"])
            if signal["type"] == SIGNAL_ACTION:
                await script_helper.async_validate_actions_config(
                    hass, cv.SCRIPT_SCHEMA(signal["actions"])
                )
        except (vol.Invalid, HomeAssistantError) as err:
            raise vol.Invalid(f"signal '{signal['id']}': {err}") from err
    try:
        if rule["activation"] and rule["activation"]["conditions"]:
            await condition_helper.async_validate_conditions_config(
                hass, cv.CONDITIONS_SCHEMA(rule["activation"]["conditions"])
            )
    except (vol.Invalid, HomeAssistantError) as err:
        raise vol.Invalid(f"activation: {err}") from err
    try:
        if rule["on_done"]:
            await script_helper.async_validate_actions_config(
                hass, cv.SCRIPT_SCHEMA(rule["on_done"])
            )
    except (vol.Invalid, HomeAssistantError) as err:
        raise vol.Invalid(f"on_done: {err}") from err
    for index, ack in enumerate(rule["acknowledge"], start=1):
        if ack["type"] != ACK_TRIGGER:
            continue
        try:
            await async_validate_triggers(hass, ack["trigger"])
        except (vol.Invalid, HomeAssistantError) as err:
            raise vol.Invalid(f"acknowledge {index}: {err}") from err
    return rule


def make_rule_id(name: str, existing: set[str]) -> str:
    """Derive a unique slug id from a rule name."""
    base = slugify(name.translate(_UMLAUTS))
    if not base or base == "unknown":  # slugify's result for "nothing usable"
        base = "rule"
    candidate, counter = base, 2
    while candidate in existing:
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate
