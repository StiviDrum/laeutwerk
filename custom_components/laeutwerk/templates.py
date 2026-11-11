"""Rule templates (built in and saved by the user) and YAML export / import."""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.yaml import dump, parse_yaml

from .compat import vol

# Keys of a rule that describe the runtime, not the configuration.
RUNTIME_KEYS = ("status",)
# Keys that are personal to an installation and left out of templates.
PERSONAL_KEYS = ("id", "sources", "enabled", "status")


def _push(title: str, message: str, done: str, later: str | None) -> dict[str, Any]:
    actions: list[dict[str, Any]] = [{"ack": True, "label": done}]
    if later:
        actions.append({"snooze": "3h", "label": later})
    return {
        "id": "push",
        "type": "notify",
        "when": "now",
        "audience": "present",
        "title": title,
        "message": message,
        "actions": actions,
    }


def _builtin_de() -> list[dict[str, Any]]:
    return [
        {
            "id": "builtin_muell",
            "name": "Müll rausstellen",
            "description": (
                "Abfallkalender: am Vorabend erinnern, bis die Tonne draußen steht."
            ),
            "rule": {
                "name": "Müll rausstellen",
                "icon": "mdi:trash-can-outline",
                "color": "#4ad295",
                "filter": {
                    "all_day": True,
                    "keywords": {
                        "columns": ["tonne", "farbe"],
                        "rows": [
                            {
                                "match": "Papier",
                                "tonne": "Papiertonne",
                                "farbe": "blau",
                            },
                            {"match": "Bio", "tonne": "Biotonne", "farbe": "braun"},
                            {
                                "match": "Rest",
                                "tonne": "Restmülltonne",
                                "farbe": "grau",
                            },
                            {"match": "Gelb", "tonne": "gelben Sack", "farbe": "gelb"},
                        ],
                    },
                },
                "reminders": [{"at": "-1d 18:00"}],
                "signals": [
                    _push(
                        "{wann}: {tonnen}",
                        "Bitte heute Abend rausstellen.",
                        "Steht draußen",
                        "Später",
                    )
                ],
                "acknowledge": [{"type": "notify_action"}],
                "ack_label": "Steht draußen",
                "bundle": True,
                "expire": "event_day 10:00",
            },
        },
        {
            "id": "builtin_geburtstag",
            "name": "Geburtstage",
            "description": "Geburtstagskalender: eine Woche vorher und am Tag selbst.",
            "rule": {
                "name": "Geburtstage",
                "icon": "mdi:cake-variant-outline",
                "color": "#c58cff",
                "filter": {"all_day": True},
                "reminders": [{"at": "-7d 09:00"}, {"at": "09:00"}],
                "signals": [
                    _push(
                        "Geburtstag",
                        "{titel} hat {wann} Geburtstag.",
                        "Gratuliert",
                        None,
                    )
                ],
                "acknowledge": [{"type": "notify_action"}],
                "ack_label": "Gratuliert",
                "bundle": False,
                "expire": "event_end",
            },
        },
        {
            "id": "builtin_wartung",
            "name": "Wartung",
            "description": (
                "Alle 90 Tage nach dem letzten Erledigen, täglich bis erledigt."
            ),
            "rule": {
                "name": "Filter tauschen",
                "icon": "mdi:air-filter",
                "color": "#6fa8ff",
                "interval": {"every": 90},
                "reminders": [{"at": "18:00"}],
                "signals": [
                    _push(
                        "{titel}", "{wann} ist es wieder so weit.", "Erledigt", "Später"
                    )
                ],
                "acknowledge": [{"type": "notify_action"}],
                "ack_label": "Erledigt",
                "bundle": True,
                "expire": "event_end",
            },
        },
        {
            "id": "builtin_medikamente",
            "name": "Medikamente-Vorrat",
            "description": "Alle 4 Wochen Rezept besorgen, drei Tage vorher erinnern.",
            "rule": {
                "name": "Medikamente nachbestellen",
                "icon": "mdi:pill",
                "color": "#ff8b4a",
                "interval": {"every": 28},
                "reminders": [{"at": "-3d 09:00"}, {"at": "09:00"}],
                "signals": [
                    _push(
                        "{titel}",
                        "Der Vorrat reicht nur noch bis {datum}.",
                        "Bestellt",
                        "Später",
                    )
                ],
                "acknowledge": [{"type": "notify_action"}],
                "ack_label": "Bestellt",
                "bundle": True,
                "expire": "event_end",
            },
        },
    ]


def _builtin_en() -> list[dict[str, Any]]:
    de = _builtin_de()
    texts = {
        "builtin_muell": (
            "Put out the bins",
            "Waste calendar: remind the evening before until the bin is outside.",
            "{wann}: {tonnen}",
            "Please put it out tonight.",
            "It's outside",
            "Later",
        ),
        "builtin_geburtstag": (
            "Birthdays",
            "Birthday calendar: a week before and on the day.",
            "Birthday",
            "{titel} has a birthday {wann}.",
            "Congratulated",
            None,
        ),
        "builtin_wartung": (
            "Maintenance",
            "Every 90 days after it was last done, daily until done.",
            "{titel}",
            "Due {wann}.",
            "Done",
            "Later",
        ),
        "builtin_medikamente": (
            "Medication supply",
            "Every 4 weeks get a prescription, remind three days before.",
            "{titel}",
            "The supply lasts until {datum}.",
            "Ordered",
            "Later",
        ),
    }
    rule_names = {
        "builtin_muell": "Put out the bins",
        "builtin_geburtstag": "Birthdays",
        "builtin_wartung": "Change the filter",
        "builtin_medikamente": "Order medication",
    }
    columns = {"Papiertonne": "paper bin", "Biotonne": "organic bin"}
    result = []
    for template in de:
        name, description, title, message, done, later = texts[template["id"]]
        rule = copy.deepcopy(template["rule"])
        rule["name"] = rule_names[template["id"]]
        rule["signals"] = [_push(title, message, done, later)]
        rule["ack_label"] = done
        for row in rule.get("filter", {}).get("keywords", {}).get("rows", []):
            row["tonne"] = columns.get(row["tonne"], row["tonne"])
        result.append(
            {**template, "name": name, "description": description, "rule": rule}
        )
    return result


def builtin_templates(language: str | None) -> list[dict[str, Any]]:
    """Templates shipped with Läutwerk, in German or English."""
    if (language or "").lower().startswith("de"):
        return _builtin_de()
    return _builtin_en()


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
