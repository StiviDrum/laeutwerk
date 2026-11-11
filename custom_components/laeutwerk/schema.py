"""Validation of rules (structure and meaning) with helpful messages."""

from __future__ import annotations

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
from .matching import EVENT_VARIABLES
from .model import (
    ACK_NOTIFY_ACTION,
    AUDIENCE_PERSONS,
    AUDIENCES,
    DEFAULT_EXPIRE,
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
    SIGNAL_ACTION,
    SIGNAL_ANNOUNCE,
    SIGNAL_LIGHT,
    SIGNAL_NOTIFY,
    SIGNAL_TYPES,
    WHEN_NOW,
)
from .timespec import KIND_EVENT_END, KIND_EVENT_START, parse_timespec

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


def _calendar_entity(value: Any) -> str:
    entity_id = cv.entity_id(value)
    if not entity_id.startswith("calendar."):
        raise vol.Invalid(f"'{entity_id}' is not a calendar entity")
    return entity_id


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

_NOTIFY_ACTION_SCHEMA = vol.Schema(
    {vol.Required("ack"): True, vol.Required("label"): _non_empty}
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
    vol.Optional("when", default=WHEN_NOW): vol.In([WHEN_NOW]),
    vol.Optional("conditions"): _conditions,
    vol.Optional("conditions_match", default=MATCH_ALL): vol.In([MATCH_ALL, MATCH_ANY]),
    vol.Optional("limit"): _LIMIT_SCHEMA,
    vol.Optional("quiet"): [_QUIET_SCHEMA],
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


_ACK_SCHEMA = vol.Schema({vol.Required("type"): vol.In([ACK_NOTIFY_ACTION])})

RULE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.slug,
        vol.Required("name"): _non_empty,
        vol.Optional("icon", default=None): vol.Any(None, cv.icon),
        vol.Optional("color", default=None): vol.Any(None, _text),
        vol.Optional("enabled", default=True): cv.boolean,
        vol.Required("sources"): vol.All(
            cv.ensure_list, [_calendar_entity], vol.Length(min=1), vol.Unique()
        ),
        vol.Optional("filter", default=dict): _FILTER_SCHEMA,
        vol.Required("reminders"): vol.All(
            cv.ensure_list,
            [vol.Schema({vol.Required("at"): _reminder_time})],
            vol.Length(min=1),
        ),
        vol.Optional("signals", default=list): _signals,
        vol.Optional("acknowledge", default=list): [_ACK_SCHEMA],
        vol.Optional("ack_label", default=None): vol.Any(None, _text),
        vol.Optional("repeat", default=REPEAT_NONE): vol.In([REPEAT_NONE]),
        vol.Optional("bundle", default=True): cv.boolean,
        vol.Optional("expire", default=DEFAULT_EXPIRE): _expire_time,
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
            if signal["type"] == SIGNAL_ACTION:
                await script_helper.async_validate_actions_config(
                    hass, cv.SCRIPT_SCHEMA(signal["actions"])
                )
        except (vol.Invalid, HomeAssistantError) as err:
            raise vol.Invalid(f"signal '{signal['id']}': {err}") from err
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
