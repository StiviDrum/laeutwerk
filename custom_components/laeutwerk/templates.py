"""Rule templates (built in and saved by the user) and YAML export / import."""

from __future__ import annotations

import copy
from datetime import date, timedelta
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.yaml import dump, parse_yaml

from .compat import vol

# Keys of a rule that describe the runtime, not the configuration.
RUNTIME_KEYS = ("status",)
# Keys that are personal to an installation and left out of templates.
PERSONAL_KEYS = ("id", "sources", "enabled", "status")


def _push(
    title: str,
    message: str,
    actions: list[dict[str, Any]],
    send_on: str = "all",
    signal_id: str = "push",
) -> dict[str, Any]:
    signal: dict[str, Any] = {
        "id": signal_id,
        "type": "notify",
        "when": "now",
        "audience": "all",
        "title": title,
        "message": message,
        "actions": actions,
    }
    if send_on != "all":
        signal["send_on"] = send_on
    return signal


def _need(path: str, domain: str, label: str, same_as: str | None = None) -> dict:
    need: dict[str, Any] = {"path": path, "domain": domain, "label": label}
    if same_as:
        need["same_as"] = same_as
    return need


def _state_trigger(to: str, duration_min: int | None = None) -> dict[str, Any]:
    trigger: dict[str, Any] = {"trigger": "state", "entity_id": "", "to": to}
    if duration_min:
        trigger["for"] = {"minutes": duration_min}
    return trigger


def _ack_trigger(to: str) -> dict[str, Any]:
    return {"type": "trigger", "trigger": [_state_trigger(to)]}


def _builtin(de: bool) -> list[dict[str, Any]]:
    def t(german: str, english: str) -> str:
        return german if de else english

    done_ack = {"ack": True, "label": t("Erledigt", "Done")}
    start = (date.today() + timedelta(days=14)).isoformat()
    bins = [
        ("Restmüll", "Residual waste", "#ff0000", "mdi:trash-can-outline"),
        ("Biomüll", "Organic waste", "#00ff00", "mdi:flower"),
        ("Altpapier", "Paper", "#2979ff", "mdi:newspaper"),
        ("Gelber Sack", "Packaging", "#ffd600", "mdi:recycle"),
    ]
    return [
        {
            "id": "builtin_muell",
            "name": t("Müll rausstellen", "Put out the bins"),
            "description": t(
                "Abfallkalender: am Vorabend erinnern, bis die Tonne draußen steht.",
                "Waste calendar: remind the evening before until it is outside.",
            ),
            "needs": [
                _need("/sources/0", "calendar", t("Abfallkalender", "Waste calendar"))
            ],
            "rule": {
                "name": t("Müll rausstellen", "Put out the bins"),
                "icon": "mdi:trash-can-outline",
                "sources": [""],
                "filter": {
                    "all_day": True,
                    "keywords": {
                        "columns": ["tonne"],
                        "rows": [
                            {
                                "match": ger,
                                "tonne": ger if de else eng,
                                "color": color,
                                "icon": icon,
                            }
                            for ger, eng, color, icon in bins
                        ],
                    },
                },
                "reminders": [{"at": "-1d 17:00"}],
                "headline": t("{wann} raus: {tonnen}", "{wann} out: {tonnen}"),
                "signals": [
                    _push(
                        t("{wann} raus: {tonnen}", "{wann} out: {tonnen}"),
                        t(
                            "{tonnen} wird morgen abgeholt!",
                            "{tonnen} will be collected tomorrow!",
                        ),
                        [{"ack": True, "label": t("Steht draußen", "It's outside")}],
                    )
                ],
                "acknowledge": [{"type": "notify_action"}],
                "ack_label": t("Steht draußen", "It's outside"),
                "escalation": [{"after": "20:00"}],
                "bundle": True,
                "expire": "event_day 10:00",
                "lookahead_days": 28,
                "early": {"mode": "hours", "hours": 2},
            },
        },
        {
            "id": "builtin_waesche",
            "name": t("Wäsche fertig", "Laundry done"),
            "description": t(
                "Waschmaschine fertig: erinnern, bis die Tür geöffnet wird.",
                "Washing machine finished: remind until the door is opened.",
            ),
            "needs": [
                _need(
                    "/start_triggers/0/entity_id",
                    "input_select",
                    t("Status der Waschmaschine", "Washing machine status"),
                ),
                _need(
                    "/acknowledge/0/trigger/0/entity_id",
                    "binary_sensor",
                    t("Türkontakt der Waschmaschine", "Washing machine door contact"),
                ),
            ],
            "rule": {
                "name": t("Wäsche fertig", "Laundry done"),
                "icon": "mdi:washing-machine",
                "start_triggers": [_state_trigger(t("Fertig", "Done"))],
                "signals": [
                    _push(
                        t("Wäsche fertig", "Laundry done"),
                        t("Wäsche ist fertig!", "The laundry is done!"),
                        [],
                        "first",
                        "push_first",
                    ),
                    _push(
                        t("Wäsche fertig", "Laundry done"),
                        t("Wäsche wartet {seit}!", "The laundry has waited {seit}!"),
                        [],
                        "repeat",
                        "push_repeat",
                    ),
                ],
                "acknowledge": [_ack_trigger("on")],
                "repeat": {"every": 30, "max": 20},
                "expire": "+12h",
            },
        },
        {
            "id": "builtin_medikament",
            "name": t("Medikament", "Medication"),
            "description": t(
                "Täglich um 8 Uhr, wiederholt bis genommen.",
                "Daily at 8 am, repeated until taken.",
            ),
            "needs": [],
            "rule": {
                "name": t("Medikament", "Medication"),
                "icon": "mdi:pill",
                "interval": {"every": 1, "start": date.today().isoformat()},
                "reminders": [{"at": "08:00"}],
                "signals": [
                    _push(
                        t("Medikament", "Medication"),
                        t("Medikament nehmen", "Take your medication"),
                        [
                            {"ack": True, "label": t("Genommen", "Taken")},
                            {"snooze": "30m", "label": t("In 30 Min.", "In 30 min")},
                        ],
                    )
                ],
                "acknowledge": [{"type": "notify_action"}],
                "ack_label": t("Genommen", "Taken"),
                "repeat": {"every": 30, "max": 4},
                "expire": "+6h",
                "early": {"mode": "hours", "hours": 1},
            },
        },
        {
            "id": "builtin_fenster",
            "name": t("Fenster offen", "Window open"),
            "description": t(
                "Fenster länger als 10 Minuten offen.",
                "Window open for more than 10 minutes.",
            ),
            "needs": [
                _need(
                    "/start_triggers/0/entity_id",
                    "binary_sensor",
                    t("Fensterkontakt", "Window contact"),
                ),
                _need(
                    "/acknowledge/0/trigger/0/entity_id",
                    "binary_sensor",
                    t("Fensterkontakt", "Window contact"),
                    same_as="/start_triggers/0/entity_id",
                ),
            ],
            "rule": {
                "name": t("Fenster offen", "Window open"),
                "icon": "mdi:window-open-variant",
                "start_triggers": [_state_trigger("on", 10)],
                "headline": t("Fenster offen seit {seit}", "Window open since {seit}"),
                "signals": [
                    _push(
                        t("Fenster offen", "Window open"),
                        t("Fenster offen seit {seit}", "Window open since {seit}"),
                        [],
                    )
                ],
                "acknowledge": [_ack_trigger("off")],
                "repeat": {"every": 15, "max": 8},
                "expire": "+12h",
            },
        },
        {
            "id": "builtin_tuer",
            "name": t("Tür nicht abgeschlossen", "Door not locked"),
            "description": t(
                "Schloss länger als 10 Minuten entriegelt.",
                "Lock unlocked for more than 10 minutes.",
            ),
            "needs": [
                _need(
                    "/start_triggers/0/entity_id", "lock", t("Türschloss", "Door lock")
                ),
                _need(
                    "/acknowledge/0/trigger/0/entity_id",
                    "lock",
                    t("Türschloss", "Door lock"),
                    same_as="/start_triggers/0/entity_id",
                ),
            ],
            "rule": {
                "name": t("Tür nicht abgeschlossen", "Door not locked"),
                "icon": "mdi:lock-open-alert-outline",
                "start_triggers": [_state_trigger("unlocked", 10)],
                "signals": [
                    _push(
                        t("Tür nicht abgeschlossen", "Door not locked"),
                        t(
                            "Die Tür ist nicht abgeschlossen!",
                            "The door is not locked!",
                        ),
                        [],
                    )
                ],
                "acknowledge": [_ack_trigger("locked")],
                "repeat": {"every": 10, "max": 12},
                "expire": "+12h",
            },
        },
        {
            "id": "builtin_geburtstag",
            "name": t("Geburtstag", "Birthday"),
            "description": t(
                "Geburtstagskalender: eine Woche vorher, am Vortag und am Tag selbst.",
                "Birthday calendar: a week before, the day before and on the day.",
            ),
            "needs": [
                _need(
                    "/sources/0",
                    "calendar",
                    t("Geburtstagskalender", "Birthday calendar"),
                )
            ],
            "rule": {
                "name": t("Geburtstag", "Birthday"),
                "icon": "mdi:cake-variant-outline",
                "sources": [""],
                "filter": {"all_day": True},
                "reminders": [
                    {"at": "-7d 09:00"},
                    {"at": "-1d 18:00"},
                    {"at": "09:00"},
                ],
                "headline": "{wann}: {titel}",
                "signals": [
                    _push(
                        "{titel}",
                        t("Nicht vergessen: {wann}.", "Don't forget: {wann}."),
                        [done_ack],
                    )
                ],
                "acknowledge": [{"type": "notify_action"}],
                "ack_label": t("Erledigt", "Done"),
                "bundle": False,
                "expire": "event_end",
                "lookahead_days": 30,
            },
        },
        {
            "id": "builtin_filter",
            "name": t("Filter wechseln", "Change filter"),
            "description": t(
                "Alle 12 Wochen, wiederholt bis gewechselt.",
                "Every 12 weeks, repeated until changed.",
            ),
            "needs": [],
            "rule": {
                "name": t("Filter wechseln", "Change filter"),
                "icon": "mdi:air-filter",
                "interval": {"every": "12w", "start": start},
                "reminders": [{"at": "09:00"}],
                "signals": [
                    _push(
                        t("Filter wechseln", "Change filter"),
                        t(
                            "Der Filter muss gewechselt werden.",
                            "Time to change the filter.",
                        ),
                        [
                            {"ack": True, "label": t("Gewechselt", "Changed")},
                            {"snooze": "1d", "label": t("Morgen", "Tomorrow")},
                        ],
                    )
                ],
                "acknowledge": [{"type": "notify_action"}],
                "ack_label": t("Gewechselt", "Changed"),
                "repeat": {"every": 1440, "max": 3},
                "expire": "+7d",
                "early": {"mode": "always"},
            },
        },
    ]


def builtin_templates(language: str | None) -> list[dict[str, Any]]:
    """Templates shipped with Läutwerk, in German or English."""
    return _builtin((language or "").lower().startswith("de"))


def fill_needs(
    rule: dict[str, Any], needs: list[dict[str, Any]], values: dict[str, str]
) -> dict[str, Any]:
    """Copy of a template rule with the entity placeholders set (path -> entity)."""
    result = copy.deepcopy(rule)
    for need in needs:
        value = values.get(need.get("same_as") or need["path"]) or values[need["path"]]
        node: Any = result
        *head, last = [p for p in need["path"].split("/") if p]
        for part in head:
            node = node[int(part)] if isinstance(node, list) else node[part]
        node[int(last) if isinstance(node, list) else last] = value
    return result


def template_from_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Rule configuration without what is personal to an installation."""
    return {k: copy.deepcopy(v) for k, v in rule.items() if k not in PERSONAL_KEYS}


def export_yaml(rules: list[dict[str, Any]]) -> str:
    """YAML of one rule (a mapping) or several rules (a list)."""
    clean = [
        {k: v for k, v in rule.items() if k not in RUNTIME_KEYS and v is not None}
        for rule in rules
    ]
    return dump(clean[0] if len(clean) == 1 else clean)


def parse_rules_yaml(text: str) -> list[dict[str, Any]]:
    """Rules from YAML (one mapping or a list); raises ``vol.Invalid``."""
    try:
        data = parse_yaml(text)
    except HomeAssistantError as err:
        raise vol.Invalid(f"invalid YAML: {err}") from err
    items = data if isinstance(data, list) else [data]
    if not items or not all(isinstance(item, dict) for item in items):
        raise vol.Invalid("YAML must contain a rule (mapping) or a list of rules")
    return [dict(item) for item in items]
