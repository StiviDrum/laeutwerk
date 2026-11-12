"""Generate custom_components/laeutwerk/translations/{en,de}.json.

The service descriptions are long (they let an assistant operate Läutwerk via
MCP); keeping them here avoids drift between English and German. Run from the
repository root after changing texts: python scripts/build_translations.py
"""

import json
import pathlib

RULE_EN = (
    "Rule object. Required: name, reminders (list of objects with 'at'; not needed for start_triggers rules) and exactly one source: sources (entity ids: calendar.*, todo.* lists with due dates, date.*, datetime.*, input_datetime.*, timestamp/date sensor.*) or interval. "
    "Optional: id, icon, color, headline and headline_plural (editable card headline with variables in curly braces, plural variant used for several hits), enabled, filter (all_day, keywords with columns = list of variable names and rows = list of objects with match, mode contains/startswith/regex, optional own color (#rrggbb) and icon (e.g. mdi:recycle) and one value per column), "
    "signals (list). Every signal: id, type, enabled, when ('now' = at the reminder time, or an object with opportunity = Home Assistant trigger(s) as in automations and manual_only = only real operation, not automations; an opportunity signal fires whenever the trigger fires while the reminder is open), conditions (Home Assistant conditions, 'only if') with conditions_match all/any, limit (per_reminder = maximum sends per reminder, min_interval = minutes between sends), quiet (list of objects with from, to as HH:MM and mode skip or defer = send when the quiet time ends). "
    "type notify: targets = list of notify.xxx actions and/or audience all/present/persons/assignee (with persons = list of person entities; uses their mobile app devices), title, title_plural, message, message_plural, actions = push buttons, list of objects with label and either ack: true or snooze: duration such as 3h, data. "
    "type light_signal: entities = light entities, pattern (effect blink/pulse, count, interval in seconds), color (name, #hex or r,g,b) or color_from = keyword column holding the colour, brightness in percent, restore (bring the light back to its previous state, default true). "
    "type announce: players = media players, text, text_plural, volume 0-100, tts = TTS entity, language, voice. "
    "type action: actions = any Home Assistant action sequence; the text variables are available as template variables. "
    "acknowledge (further ways to acknowledge, list of objects: type tag with tag_id = NFC tag; type trigger with trigger = Home Assistant trigger such as a door contact, zone or button), "
    "repeat ('none' or an object with every = minutes or a duration such as 1h, and max = number of repetitions), "
    "interval (every = days such as 90 or '12w', start = first due date: due again that many days after the last acknowledgement; overdue = reminds daily), "
    "activation (conditions, match all/any, season with from/to as MM-DD: the rule is only active then), on_done (Home Assistant actions run when acknowledged, variables plus person and via), "
    "assignee (persons = person entities, rotation fixed/weekly/per_event/after_last, substitute = person that takes over at the first reminder if substitute_when (entity_id and state) holds; text variable zustaendig, push audience 'assignee'), "
    "escalation (list of stages with after = duration such as 2h or time of day such as 21:30, counted from the first reminder, and optional color = #rrggbb shown in the card; a signal with stage n starts with that stage), "
    "start_triggers (list of Home Assistant triggers as in automations; instead of calendars the rule starts a reminder whenever one fires and none is open; reminders and filter are ignored, expire defaults to '+12h' and must not be event_start/event_end; start it by hand with the start action), early (object with mode off, hours or always, default hours with hours 1-720, default 24: when a planned reminder may be acknowledged before its time; ignored by trigger rules), early_feedback (object with message and clear_after seconds 0-3600, default 10, or null: short push after a too early attempt to the person, else the assignee; variables of the next planned reminder), confirm (object with message and clear_after seconds 0-3600, default 10: confirmation push to whoever acknowledged, else the assignee), expire also accepts a plus sign and a duration such as '+12h' (after the start), "
    "lookahead_days (1-365, default 14, days the calendars are read ahead, must exceed the earliest reminder offset), visible (default true; false hides the rule in the card overview), "
    "ack_label, bundle (events of the same day become one reminder, default true), expire (default event_end). "
    "Times: '-1d 17:00' (day before at 17:00), '09:00' (event day), '-2h' (before the start), 'event_day 12:00', 'event_end'. "
    "Text variables, written in curly braces in the texts: titel, rest, beschreibung, ort, kalender, wann, datum, uhrzeit, one per keyword column and its plural with an appended n (e.g. tonne / tonnen)."
)
RULE_DE = (
    "Regel-Objekt. Pflicht: name, reminders (Liste von Objekten mit 'at'; bei start_triggers-Regeln nicht nötig) und genau eine Quelle: sources (Entitäten: calendar.*, todo.*-Listen mit Fälligkeit, date.*, datetime.*, input_datetime.*, Zeitstempel-/Datums-sensor.*) oder interval. "
    "Optional: id, icon, color, headline und headline_plural (bearbeitbare Überschrift der Karte mit Variablen in geschweiften Klammern, Mehrzahl-Variante bei mehreren Treffern), enabled, filter (all_day, keywords mit columns = Liste der Variablennamen und rows = Liste von Objekten mit match, mode contains/startswith/regex, optional eigener color (#rrggbb) und icon (z. B. mdi:recycle) und einem Wert je Spalte), "
    "signals (Liste). Jedes Signal: id, type, enabled, when ('now' = zum Erinnerungszeitpunkt, oder ein Objekt mit opportunity = Home-Assistant-Trigger wie in Automationen und manual_only = nur echte Bedienung, keine Automationen; ein Gelegenheits-Signal feuert immer dann, wenn der Trigger auslöst, solange die Erinnerung offen ist), conditions (Home-Assistant-Bedingungen, „nur wenn“) mit conditions_match all/any, limit (per_reminder = höchstens so oft pro Erinnerung, min_interval = Minuten Mindestabstand), quiet (Liste von Objekten mit from, to als HH:MM und mode skip oder defer = nachholen, sobald die Ruhezeit endet). "
    "type notify: targets = Liste von notify.xxx-Aktionen und/oder audience all/present/persons/assignee (mit persons = Liste von Personen-Entitäten; nutzt deren Mobile-App-Geräte), title, title_plural, message, message_plural, actions = Push-Knöpfe, Liste von Objekten mit label und entweder ack: true oder snooze: Dauer wie 3h, data. "
    "type light_signal: entities = Licht-Entitäten, pattern (effect blink/pulse, count, interval in Sekunden), color (Name, #hex oder r,g,b) oder color_from = Stichwort-Spalte mit der Farbe, brightness in Prozent, restore (Licht danach in den vorherigen Zustand bringen, Standard true). "
    "type announce: players = Mediaplayer, text, text_plural, volume 0-100, tts = TTS-Entität, language, voice. "
    "type action: actions = beliebige Home-Assistant-Aktionsfolge; die Textvariablen stehen als Template-Variablen bereit. "
    "acknowledge (weitere Quittierwege, Liste von Objekten: type tag mit tag_id = NFC-Tag; type trigger mit trigger = Home-Assistant-Trigger wie Türkontakt, Zone oder Taster), "
    "repeat ('none' oder ein Objekt mit every = Minuten oder Dauer wie 1h, und max = Anzahl Wiederholungen), "
    "interval (every = Tage wie 90 oder '12w', start = erste Fälligkeit: wieder fällig so viele Tage nach dem letzten Quittieren; überfällig = täglich erinnern), "
    "activation (conditions, match all/any, season mit from/to als MM-TT: Regel nur dann aktiv), on_done (Home-Assistant-Aktionen beim Quittieren, Variablen plus person und via), "
    "assignee (persons = Personen-Entitäten, rotation fixed/weekly/per_event/after_last, substitute = Vertretung, die bei der ersten Erinnerung übernimmt, wenn substitute_when (entity_id and state) zutrifft; Textvariable zustaendig, Push-Zielgruppe 'assignee'), "
    "escalation (Liste von Stufen mit after = Dauer wie 2h oder Uhrzeit wie 21:30, gezählt ab der ersten Erinnerung, und optional color = #rrggbb für die Karte; ein Signal mit stage n startet mit dieser Stufe), "
    "start_triggers (Liste von Home-Assistant-Triggern wie in Automationen; statt Kalendern startet die Regel eine Erinnerung, sobald einer auslöst und keine offen ist; reminders und filter werden ignoriert, expire ist standardmäßig '+12h' und darf nicht event_start/event_end sein; von Hand mit der Aktion start), early (Objekt mit mode off, hours oder always, Standard hours mit hours 1-720, Standard 24: wann eine geplante Erinnerung schon vor ihrer Zeit quittiert werden darf; bei Auslöser-Regeln ohne Wirkung), early_feedback (Objekt mit message und clear_after Sekunden 0-3600, Standard 10, oder null: kurze Push nach einem zu frühen Versuch an die Person, sonst an die Zuständigen; Variablen der nächsten geplanten Erinnerung), confirm (Objekt mit message und clear_after Sekunden 0-3600, Standard 10: Bestätigungs-Push an die erledigende Person, sonst an die Zuständigen), expire kennt auch ein Pluszeichen mit Dauer wie '+12h' (nach dem Start), "
    "lookahead_days (1-365, Standard 14, Tage, die der Kalender vorausgelesen wird, muss größer als die früheste Erinnerung sein), visible (Standard true; false blendet die Regel in der Kartenübersicht aus), "
    "ack_label, bundle (Termine desselben Tages werden eine Erinnerung, Standard true), expire (Standard event_end). "
    "Zeiten: '-1d 17:00' (Vortag 17:00), '09:00' (am Termintag), '-2h' (vor Beginn), 'event_day 12:00', 'event_end'. "
    "Textvariablen, in den Texten in geschweiften Klammern: titel, rest, beschreibung, ort, kalender, wann, datum, uhrzeit, je Stichwort-Spalte eine und ihre Mehrzahl mit angehängtem n (z. B. tonne / tonnen)."
)


def svc(title, desc, **fields):
    return {
        "name": title,
        "description": desc,
        "fields": {k: {"name": v[0], "description": v[1]} for k, v in fields.items()},
    }


en = {
    "config": {
        "step": {
            "user": {
                "title": "Läutwerk",
                "description": "Set up Läutwerk? Rules are created afterwards in the Läutwerk card on a dashboard.",
            }
        },
        "abort": {"single_instance_allowed": "Läutwerk is already set up."},
    },
    "options": {
        "step": {
            "init": {
                "title": "Household quiet time",
                "description": "Signals without their own quiet time follow this one. Leave both times empty for none.",
                "data": {
                    "from": "From",
                    "to": "To",
                    "mode": "Signals in the quiet time",
                },
                "data_description": {
                    "mode": "Skip them, or send them when the quiet time ends."
                },
            }
        },
        "error": {"incomplete": "Enter both times or none."},
    },
    "selector": {
        "quiet_mode": {"options": {"skip": "Skip", "defer": "Send when it ends"}}
    },
    "entity": {
        "sensor": {
            "state": {
                "state": {
                    "planned": "Planned",
                    "reminded": "Reminded",
                    "done": "Done",
                    "missed": "Missed",
                    "inactive": "Inactive",
                }
            },
            "next_event": {"name": "Next event"},
            "open_total": {"name": "Open reminders"},
        },
        "binary_sensor": {"open": {"name": "Open"}},
        "button": {"done": {"name": "Done"}},
        "switch": {"rule": {"name": "Active"}},
    },
    "services": {
        "acknowledge": svc(
            "Acknowledge",
            "Marks reminders as done. With 'rule': the open reminders of that rule (or its next planned reminder, as far as the early setting of the rule allows it). Without 'rule': all open reminders of all rules. Returns acknowledged (reminder ids) and too_early (text such as the next due date when it was too early, else null) when response data is requested.",
            rule=("Rule", "Rule id (see get_rules). Empty: all open reminders."),
            reminder_id=(
                "Reminder",
                "Acknowledge exactly this reminder (id from get_rules → status.reminders).",
            ),
            person=(
                "Person",
                "Name stored as 'acknowledged by'. Default: the person of the calling user.",
            ),
        ),
        "snooze": svc(
            "Snooze",
            "Reminds again later: open reminders become planned again and remind once more when the duration is over or at the given time (unless they expire first). Give either 'duration' or 'until'. Without 'rule': all open reminders.",
            rule=("Rule", "Rule id. Empty: all open reminders."),
            reminder_id=("Reminder", "Snooze exactly this reminder."),
            duration=("Duration", "Minutes, or a duration such as 30m, 3h, 1d."),
            until=("Until", "Time of day, e.g. 07:00 (the next time it is reached)."),
        ),
        "reopen": svc(
            "Reopen",
            "Undoes the acknowledgement of a reminder (e.g. a mis-tap) as long as it has not expired: it is open again (reminded or planned). Signals are not sent again; actions run when done are not undone.",
            reminder_id=(
                "Reminder",
                "Id of the acknowledged reminder (get_rules → status.reminders).",
            ),
        ),
        "trigger": svc(
            "Trigger",
            "Reminds now: sends the immediate signals of the rule for its open or next planned reminder, regardless of the reminder times.",
            rule=("Rule", "Rule id."),
        ),
        "start": svc(
            "Start",
            "Starts a reminder of a rule that is driven by start_triggers, exactly as if a trigger had fired: nothing happens while a reminder of the rule is open. Fails for rules without start_triggers.",
            rule=("Rule", "Rule id."),
        ),
        "test_signal": svc(
            "Test signal",
            "Sends one signal of a rule right now, ignoring its conditions, quiet times and limits. Uses the open reminder, else the next matching event, else a sample event for tomorrow. Give either 'signal' (id of a saved signal) or 'config' (a signal object that is not saved, requires admin).",
            rule=("Rule", "Rule id."),
            signal=("Signal", "Id of a signal of the rule."),
            config=(
                "Signal object",
                "Unsaved signal to try out (same fields as a signal in create_rule).",
            ),
        ),
        "get_rules": svc(
            "Get rules",
            "Returns the rules (configuration as used by create_rule/update_rule) with their runtime status: state (planned/reminded/done/missed/inactive), reminders with variables, next matching event, calendar errors.",
            rule=("Rule", "One or more rule ids. Empty: all rules."),
        ),
        "create_rule": svc(
            "Create rule",
            "Creates a rule and returns its id. Requires admin.",
            config=("Rule", RULE_EN),
        ),
        "update_rule": svc(
            "Update rule",
            "Changes a rule: the given top-level keys replace the stored ones (e.g. only 'signals' or 'reminders'); open reminders are kept. Requires admin.",
            rule=("Rule", "Rule id."),
            config=(
                "Changes",
                "Top-level keys of the rule object to replace. " + RULE_EN,
            ),
        ),
        "delete_rule": svc(
            "Delete rule",
            "Deletes a rule with its reminders and entities. Requires admin.",
            rule=("Rule", "Rule id."),
        ),
        "duplicate_rule": svc(
            "Duplicate rule",
            "Copies a rule; the copy is switched off. Returns the new id. Requires admin.",
            rule=("Rule", "Rule id to copy."),
            name=("Name", "Name of the copy."),
            new_rule=("New id", "Id of the copy (default: derived from the name)."),
        ),
        "export_rules": svc(
            "Export rules",
            "Returns rules as YAML (one rule as a mapping, several as a list) – for backups or to copy them to another Home Assistant.",
            rule=("Rule", "One or more rule ids. Empty: all rules."),
        ),
        "import_rules": svc(
            "Import rules",
            "Creates rules from YAML as returned by export_rules. Ids that exist already get a new one. All rules are checked first; if one is invalid, none is created. Requires admin.",
            yaml=("YAML", "One rule (mapping) or a list of rules."),
        ),
        "enable": svc(
            "Enable",
            "Switches rules on.",
            rule=("Rule", "One or more rule ids. Empty: all rules."),
        ),
        "disable": svc(
            "Disable",
            "Switches rules off; their open reminders are dropped.",
            rule=("Rule", "One or more rule ids. Empty: all rules."),
        ),
    },
    "exceptions": {
        "not_loaded": {"message": "Läutwerk is not set up."},
        "unknown_rule": {"message": "Unknown rule: {rule}"},
        "rule_disabled": {"message": "Rule {rule} is switched off."},
        "not_trigger_rule": {"message": "Rule {rule} has no start_triggers."},
        "no_upcoming_event": {
            "message": "Rule {rule} has no upcoming event to remind of."
        },
        "signal_or_config": {"message": "Give either 'signal' or 'config'."},
        "signal_failed": {
            "message": "The signal could not be sent – see the log for details."
        },
        "duration_or_until": {"message": "Give either 'duration' or 'until'."},
        "cannot_reopen": {
            "message": "Reminder {reminder} cannot be reopened (not acknowledged or already expired)."
        },
    },
    "issues": {
        "missing_entities": {
            "title": 'Läutwerk rule "{rule}" refers to missing entities',
            "description": 'The rule "{rule}" uses entities or actions that do not exist (any more): {entities}.\n\nCalendars that are missing are not read, signals to missing lights, speakers or phones are not sent. Restore them or edit the rule in the Läutwerk card. This message disappears as soon as everything is available again.',
        },
    },
}
de = {
    "config": {
        "step": {
            "user": {
                "title": "Läutwerk",
                "description": "Läutwerk einrichten? Regeln legst du danach in der Läutwerk-Karte auf einem Dashboard an.",
            }
        },
        "abort": {"single_instance_allowed": "Läutwerk ist bereits eingerichtet."},
    },
    "options": {
        "step": {
            "init": {
                "title": "Ruhezeit des Haushalts",
                "description": "Signale ohne eigene Ruhezeit richten sich danach. Beide Zeiten leer lassen für keine.",
                "data": {"from": "Von", "to": "Bis", "mode": "Signale in der Ruhezeit"},
                "data_description": {
                    "mode": "Auslassen oder senden, sobald die Ruhezeit endet."
                },
            }
        },
        "error": {"incomplete": "Beide Zeiten angeben oder keine."},
    },
    "selector": {
        "quiet_mode": {
            "options": {"skip": "Auslassen", "defer": "Senden, wenn sie endet"}
        }
    },
    "entity": {
        "sensor": {
            "state": {
                "state": {
                    "planned": "Geplant",
                    "reminded": "Erinnert",
                    "done": "Erledigt",
                    "missed": "Verpasst",
                    "inactive": "Inaktiv",
                }
            },
            "next_event": {"name": "Nächster Termin"},
            "open_total": {"name": "Offene Erinnerungen"},
        },
        "binary_sensor": {"open": {"name": "Offen"}},
        "button": {"done": {"name": "Erledigt"}},
        "switch": {"rule": {"name": "Aktiv"}},
    },
    "services": {
        "acknowledge": svc(
            "Quittieren",
            "Markiert Erinnerungen als erledigt. Mit 'rule': die offenen Erinnerungen dieser Regel (oder ihre nächste geplante Erinnerung, soweit die Einstellung early der Regel es erlaubt). Ohne 'rule': alle offenen Erinnerungen aller Regeln. Liefert auf Wunsch acknowledged (Erinnerungs-IDs) und too_early (Text mit dem nächsten Termin, wenn es zu früh war, sonst null) zurück.",
            rule=(
                "Regel",
                "Regel-ID (siehe get_rules). Leer: alle offenen Erinnerungen.",
            ),
            reminder_id=(
                "Erinnerung",
                "Genau diese Erinnerung quittieren (ID aus get_rules → status.reminders).",
            ),
            person=(
                "Person",
                "Name, der als „erledigt von“ gespeichert wird. Standard: die Person des aufrufenden Benutzers.",
            ),
        ),
        "snooze": svc(
            "Später erinnern",
            "Erinnert später noch einmal: offene Erinnerungen werden wieder „geplant“ und erinnern erneut, wenn die Dauer um ist oder zur angegebenen Uhrzeit (sofern sie nicht vorher verfallen). Entweder 'duration' oder 'until' angeben. Ohne 'rule': alle offenen Erinnerungen.",
            rule=("Regel", "Regel-ID. Leer: alle offenen Erinnerungen."),
            reminder_id=("Erinnerung", "Genau diese Erinnerung zurückstellen."),
            duration=("Dauer", "Minuten oder eine Dauer wie 30m, 3h, 1d."),
            until=(
                "Bis",
                "Uhrzeit, z. B. 07:00 (das nächste Mal, dass sie erreicht wird).",
            ),
        ),
        "reopen": svc(
            "Wieder öffnen",
            "Nimmt das Quittieren einer Erinnerung zurück (z. B. nach einem Fehltipp), solange sie nicht verfallen ist: sie ist wieder offen (erinnert oder geplant). Signale werden nicht erneut gesendet, Aktionen beim Erledigen nicht rückgängig gemacht.",
            reminder_id=(
                "Erinnerung",
                "ID der quittierten Erinnerung (get_rules → status.reminders).",
            ),
        ),
        "trigger": svc(
            "Auslösen",
            "Erinnert sofort: sendet die Sofort-Signale der Regel für ihre offene oder nächste geplante Erinnerung, unabhängig von den Erinnerungszeitpunkten.",
            rule=("Regel", "Regel-ID."),
        ),
        "start": svc(
            "Starten",
            "Startet eine Erinnerung einer Regel mit start_triggers, genau als hätte ein Trigger ausgelöst: solange eine Erinnerung der Regel offen ist, passiert nichts. Fehler bei Regeln ohne start_triggers.",
            rule=("Regel", "Regel-ID."),
        ),
        "test_signal": svc(
            "Signal testen",
            "Sendet ein Signal einer Regel sofort, ohne Bedingungen, Ruhezeiten und Grenzen zu beachten. Nutzt die offene Erinnerung, sonst den nächsten passenden Termin, sonst einen Beispieltermin für morgen. Entweder 'signal' (ID eines gespeicherten Signals) oder 'config' (ein nicht gespeichertes Signal-Objekt, nur Admin) angeben.",
            rule=("Regel", "Regel-ID."),
            signal=("Signal", "ID eines Signals der Regel."),
            config=(
                "Signal-Objekt",
                "Ungespeichertes Signal zum Ausprobieren (gleiche Felder wie ein Signal in create_rule).",
            ),
        ),
        "get_rules": svc(
            "Regeln abrufen",
            "Liefert die Regeln (Konfiguration wie bei create_rule/update_rule) mit Laufzeitstatus: Zustand (planned/reminded/done/missed/inactive), Erinnerungen mit Variablen, nächster passender Termin, Kalenderfehler.",
            rule=("Regel", "Eine oder mehrere Regel-IDs. Leer: alle Regeln."),
        ),
        "create_rule": svc(
            "Regel anlegen",
            "Legt eine Regel an und liefert ihre ID. Nur Admin.",
            config=("Regel", RULE_DE),
        ),
        "update_rule": svc(
            "Regel ändern",
            "Ändert eine Regel: die angegebenen Schlüssel der obersten Ebene ersetzen die gespeicherten (z. B. nur 'signals' oder 'reminders'); offene Erinnerungen bleiben erhalten. Nur Admin.",
            rule=("Regel", "Regel-ID."),
            config=(
                "Änderungen",
                "Zu ersetzende Schlüssel der obersten Ebene des Regel-Objekts. "
                + RULE_DE,
            ),
        ),
        "delete_rule": svc(
            "Regel löschen",
            "Löscht eine Regel samt Erinnerungen und Entitäten. Nur Admin.",
            rule=("Regel", "Regel-ID."),
        ),
        "duplicate_rule": svc(
            "Regel duplizieren",
            "Kopiert eine Regel; die Kopie ist ausgeschaltet. Liefert die neue ID. Nur Admin.",
            rule=("Regel", "ID der zu kopierenden Regel."),
            name=("Name", "Name der Kopie."),
            new_rule=("Neue ID", "ID der Kopie (Standard: aus dem Namen abgeleitet)."),
        ),
        "export_rules": svc(
            "Regeln exportieren",
            "Liefert Regeln als YAML (eine Regel als Objekt, mehrere als Liste) – zur Sicherung oder zum Übertragen in ein anderes Home Assistant.",
            rule=("Regel", "Eine oder mehrere Regel-IDs. Leer: alle Regeln."),
        ),
        "import_rules": svc(
            "Regeln importieren",
            "Legt Regeln aus YAML an, wie es export_rules liefert. Vorhandene IDs bekommen eine neue. Alle Regeln werden vorher geprüft; ist eine ungültig, wird keine angelegt. Nur Admin.",
            yaml=("YAML", "Eine Regel (Objekt) oder eine Liste von Regeln."),
        ),
        "enable": svc(
            "Einschalten",
            "Schaltet Regeln ein.",
            rule=("Regel", "Eine oder mehrere Regel-IDs. Leer: alle Regeln."),
        ),
        "disable": svc(
            "Ausschalten",
            "Schaltet Regeln aus; ihre offenen Erinnerungen werden verworfen.",
            rule=("Regel", "Eine oder mehrere Regel-IDs. Leer: alle Regeln."),
        ),
    },
    "exceptions": {
        "not_loaded": {"message": "Läutwerk ist nicht eingerichtet."},
        "unknown_rule": {"message": "Unbekannte Regel: {rule}"},
        "rule_disabled": {"message": "Die Regel {rule} ist ausgeschaltet."},
        "not_trigger_rule": {"message": "Die Regel {rule} hat keine start_triggers."},
        "no_upcoming_event": {
            "message": "Die Regel {rule} hat keinen anstehenden Termin, an den erinnert werden könnte."
        },
        "signal_or_config": {"message": "Entweder 'signal' oder 'config' angeben."},
        "signal_failed": {
            "message": "Das Signal konnte nicht gesendet werden – Details stehen im Protokoll."
        },
        "duration_or_until": {"message": "Entweder 'duration' oder 'until' angeben."},
        "cannot_reopen": {
            "message": "Die Erinnerung {reminder} lässt sich nicht wieder öffnen (nicht quittiert oder schon verfallen)."
        },
    },
    "issues": {
        "missing_entities": {
            "title": "Läutwerk-Regel „{rule}“ verweist auf Fehlendes",
            "description": "Die Regel „{rule}“ verwendet Entitäten oder Aktionen, die es (nicht mehr) gibt: {entities}.\n\nFehlende Kalender werden nicht gelesen, Signale an fehlende Lampen, Lautsprecher oder Handys nicht gesendet. Stelle sie wieder her oder bearbeite die Regel in der Läutwerk-Karte. Diese Meldung verschwindet, sobald alles wieder vorhanden ist.",
        },
    },
}
for lang, data in (("en", en), ("de", de)):
    pathlib.Path(f"custom_components/laeutwerk/translations/{lang}.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    )
