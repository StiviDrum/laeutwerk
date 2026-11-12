# TASKS.md – Läutwerk milestone checklist

Tick boxes as you go (`- [x]`), short findings below the task. A new session reads `CLAUDE.md` + this file and continues at the next open item.

## M0 – Scaffold
- [x] Repo-Link erfragt, Werkzeuge geprüft, Zeitwerk als Referenz geklont
  - Repo: https://github.com/StiviDrum/laeutwerk (was empty). Reference: existing `~/zeitwerk` (1.0.0-rc.3).
  - WSL2: git 2.43, Node 22, Python 3.14.10 (`python3.14`; system `python3` is 3.12 and too old for HA). `gh` is not installed – only needed for convenience (checking CI/releases from the shell); `sudo apt install gh && gh auth login`.
- [x] Struktur wie Zeitwerk (`custom_components/laeutwerk`, `frontend/`, `tests/`, `scripts/`, `config/`, `docs/`), `docs/SPEC.md`, `DESIGN.md`, `TASKS.md` aus dieser Datei
- [x] `manifest.json`, `hacs.json`, `pyproject.toml`, Frontend-Tooling, Lint, Tests
  - Decision: minimum Home Assistant is 2026.11.0 (tests use the official `pytest-homeassistant` 2026.11.1, which pins HA 2026.11.1). No compatibility job for older HA versions, unlike Zeitwerk – lower the minimum only together with a CI job that tests it.
  - `compat.py` (probatio/voluptuous import) kept from Zeitwerk.
- [x] CI (`validate.yml`, `release.yml` mit ZIP, kein Pre-Release)
  - `release.yml` sets `prerelease: false` + `make_latest: true` for every tag.
- [x] Testinstanz-Config mit Kalendern und Stand-in-Helfern (A4)
  - Local calendars cannot be configured in YAML → `scripts/seed_dev_config.py` (run by `scripts/develop`) writes the ICS files (recurring events, Papier + Bio share a day every 4 weeks) and the config entries for both calendars and Läutwerk on a fresh `./config`.
  - Entities: `calendar.abfallkalender`, `calendar.kult61`, `light.stehleuchte` (template light with colour), `binary_sensor.haustuer` (from `input_boolean.haustuer`), `input_boolean.steven_home` / `person_2_home`.
  - Still missing for later milestones: a notify target (0.1: `notify.persistent_notification` or a notify group as stand-in for the mobile app) and a media player + TTS for announcements (0.2).
- [x] LICENSE, README-Gerüst (en + de), CHANGELOG; erster Push, CI grün

## 0.1 – Kern
- [x] Model, Store mit Migrationen, Config-Flow (Single Instance)
  - `model.py` (Rule, Filter, KeywordRow, Signal, CalendarEvent, Reminder), `schema.py` (validation), `store.py` (rules + reminders per rule).
- [x] Kalender lesen (`calendar.get_events`, 14 Tage voraus, alle 15 min und bei Änderung), Filter, Stichwort-Tabelle, Variablen inkl. Mehrzahl
  - `sources.py`, `matching.py` (pure). Calendars expose no uid: event identity = calendar + start + title. Reminder id = `<rule>__<YYYYMMDD>` (bundle) or with a hash suffix (no bundle).
  - `{titel}` / `{rest}` are joined over all bundled events; text starting with a variable is capitalised ("Morgen: …").
- [x] Erinnerungs-Lebenszyklus (B5), Zeitpunkte als Timer, Bündeln, Verfallen, Neustart-fest
  - `timespec.py`: `-1d 17:00`, `09:00`, `event_day 12:00`, `-2h`, `-7d`, `event_start`, `event_end` (default expiry). DST: gap -> first valid instant, repeated hour -> first pass.
  - `engine.py` (RuleRunner, one timer per rule). Sent reminder times are stored per reminder (`fired`) -> no duplicates after restart; missed reminder times are caught up once. Events already expired when found create no reminder.
  - Early acknowledge (planned -> done) is allowed from 24 h before the first reminder time (`EARLY_ACK_HOURS`).
  - Switching a rule off drops its open reminders.
- [x] Signal Push (sofort), Quittieren per Knopf, Dienst, Push-Aktion
  - 0.1: `targets` = list of `notify.xxx` actions (audience comes with 0.2). Push carries `tag` + action `LAEUTWERK_ACK__<reminder id>`; on done/missed the notification is cleared on `notify.mobile_app_*` targets.
- [x] Entitäten, Dienste (inkl. `get_rules`), Ereignisse
  - Services: acknowledge, trigger, get_rules, create_rule, update_rule, delete_rule, duplicate_rule, enable, disable. `snooze` (0.3) and `test_signal` (0.2) follow. WebSocket API follows with the card (0.4).
- [x] Tests inkl. Sommer-/Winterzeit; Release v0.1.0
  - Checked in the dev instance with the real local calendars: reference rules seeded into `.storage/laeutwerk`, "Gelb" (tomorrow) was reminded once via `notify.persistent_notification`, the other events are planned, all ten entities exist, no errors in the log.

## 0.2 – Signale
- [x] Licht-Signal (Muster, Farbe aus Spalte, Zustand wiederherstellen), Ansage (TTS announce, Lautstärke, Einzahl/Mehrzahl-Text), eigene Aktion
  - `signals.py` (one sender per type), `colors.py` (German/English names, hex, r,g,b; grey/black -> white).
  - Light: `entity` (short form) is stored as `entities`. One signal per lamp at a time. A lamp that was off is switched off again – its "last colour" may then be the signal colour on bulbs that remember it (cannot be restored without switching on).
  - Announcement: `media_player.play_media` with a TTS media source id and `announce: true` (what `tts.speak` does) so that `extra.volume` can be passed; only players that support announcement volume (Sonos) use it.
  - Custom action: `Script` with the text variables as run variables.
- [x] Ruhezeiten (auslassen/nachholen), Zielgruppe, Häufigkeit
  - Quiet `mode: skip | defer`; deferred signals are stored per reminder and sent when the quiet time ends, if the reminder is still open (also after a restart).
  - `limit: {per_reminder, min_interval (minutes)}`; "only if" conditions (`conditions`, `conditions_match`) are part of every signal already. Conditions and action sequences are fully validated when a rule is saved (HA's condition validation is asynchronous).
  - Audience `all | present | persons`: person -> `device_trackers` of the mobile app -> legacy action `notify.mobile_app_<device>` (the notify entity cannot carry action buttons).
- [x] `test_signal`; Release v0.2.0
  - `rule` + `signal` (saved) or `config` (unsaved, admin). Uses the open reminder, else the next event, else a sample event for tomorrow.
  - Dev instance: light signal can be watched on `light.stehleuchte`. No media player / TTS stand-in yet (the demo integration would add dozens of entities) – announcements are covered by tests only so far.

## 0.3 – Gelegenheiten und Quittierung
- [x] „Bei Gelegenheit“ mit beliebigem HA-Trigger, Zeitfenster, `manual_only` über `context`, `{person}`
  - `when: {opportunity: <trigger(s)>, manual_only}`. `triggers.py`: `TriggerListener` attaches the triggers only while a reminder is reminding and detaches them afterwards.
  - Manual = context without `parent_id` (automations/scripts act with a child context). Läutwerk's own signals use registered contexts (`own_context`) and are never an opportunity – verified with a real template light in `tests/test_real_light.py` (blink, restore, no self-trigger).
  - `{person}`: changed person entity, person of a device tracker, else the person of the acting user; empty if unknown.
- [x] Wiederholen, Snooze
  - `repeat: none | {every: <minutes or 1h>, max: 24}`: re-sends the "now" signals (limits and quiet times apply), event `laeutwerk_reminded` with `reminder_time: repeat`.
  - Snooze: reminded -> planned with `snoozed_until`; regular reminder times in between are skipped; expiry still applies; "done" works while snoozed. `signals_sent` is kept, so `per_reminder` limits also hold after a snooze.
- [x] Quittierung per NFC-Tag, Türkontakt, Zone, Taster
  - `acknowledge: [{type: tag, tag_id}, {type: trigger, trigger, early}]`. Tag and button also work before the reminder time (24 h window), triggers only with `early: true`.
- [x] Release v0.3.0

## 0.4 – Karte
- [x] Ansicht „Heute & demnächst“ inkl. Leerzustand, Live-Updates
  - One `laeutwerk/rules/subscribe` per card (unsubscribed in `disconnectedCallback`); rule status (reminders with variables, colours, next times) comes with every rule. `shouldUpdate` ignores `hass` updates (only language/theme/admin), except while the editor is open (entity pickers).
  - "Later" = `laeutwerk.snooze` 3 h; done = `laeutwerk.acknowledge` with the reminder id and the user's name.
  - Colour dots: column of the light signal's `color_from`, else a column named farbe/color (backend `hit_colors`, German names → hex).
- [x] Regel-Editor mit Stichwort-Tabelle (horizontal scrollbar), Vorschau (`laeutwerk/preview`), Signal-Liste
  - Preview works for unsaved rules (debounced 500 ms). Renaming a column also renames it in the rows and in `color_from`.
- [x] Signal-Editor mit HA-Trigger-/Bedingungs-/Aktions-Editor, YAML-Ansicht
  - `laeutwerk-field` wraps `ha-selector` (trigger/condition/action/entity/icon/object) and falls back to text/JSON fields when HA's selectors are not loaded (preview page).
  - Test uses `laeutwerk.test_signal` with the unsaved signal config (needs a saved rule).
- [x] Release v0.4.0 → Steven kann die Müll-Regel parallel zur bestehenden Automation testen
  - Layout checked with `frontend/dev/preview.html` (mocked hass) in headless Chromium at 390 px, dark + light: overview, editor, signal editor, compact, empty. Fixed: overflowing footer, squeezed rows.
  - Checked in the real HA 2026.11 frontend (dev instance, `scripts/check_card.py`): card loads, `ha-selector` is available inside the card – trigger editor, condition editor, entity and icon pickers render in the rule and signal editors.
  - Bundle: 26 KB gzip.

## Findings (CI)
- 2026-11-11: pytest was red in CI since 0.2 although green locally: `scripts/develop` lets Home Assistant install component requirements (e.g. `mutagen` for TTS) into `.venv`, CI does not have them. Tests must not import optional components (`tts` is mocked via `signals._media_source_id`). Check suspicious failures in a clean venv from `requirements_test.txt`.
- HACS validation needs a repository description (set 2026-11-11 with `gh repo edit`). CI fully green since then.

## 0.5 – Feinschliff
- [x] Verlauf je Regel, Kompakt-Modus, visueller Karteneditor
  - History: up to 50 finished reminders per rule in storage 1.2 (`history`, migration from 1.1 tested), websocket `laeutwerk/history`; shown in `view: rule`, reloaded when the rule's reminders change.
  - Compact mode came with 0.4. Card editor: `ha-form` with fallback; `cleanCardConfig` drops keys of the other view.
- [x] Übersetzungen de/en vollständig, Reparaturen, Diagnose
  - Repair issue `missing_entities` per enabled rule: missing entities (sources, lights, players, persons, TTS, entity ids in conditions/triggers/actions) and missing notify actions; re-checked on rule changes and entity registry updates.
  - Diagnostics: rules, status, history, references, invalid stored rules.
  - Text variables (`{wann}` …) follow the **server** language (`hass.config.language`), the card UI the user's language. Dev instance now `language: de`.
- [x] Release v0.5.0
  - Bundle: 27 KB gzip.

## 0.6 – Erweiterungen (B7)
- [x] Intervall ab Erledigung
  - `interval: {every (days, '12w'), start}`; without start the first due day is the day the rule is saved (kept on updates). Pseudo source `interval` (bypasses the keyword filter); last done = newest "done" entry of the history. Overdue → carried to today (new reminder each day until done; yesterday's one is missed).
- [x] Eskalationsstufen
  - `escalation: [{after: '2h' | '21:30'}]`, counted from `reminded_at` (time of day on that local day; already passed → immediately). Signal `stage: n` is active from stage n (now-signals sent when the stage starts, opportunity signals armed). `Reminder.stage` persisted; event `laeutwerk_reminded` with `reminder_time: stage_n`.
- [x] Zuständigkeit und Wechsel
  - `assignee: {persons, rotation}`; fixed per reminder at creation (`Reminder.assignee`). `per_event` = history length + earlier open reminders; `weekly` = calendar week of the event day; `after_last` = next after the last acknowledger (by person name). `{zustaendig}`, audience `assignee`, `status.assignee_stats` from the history.
- [x] Aktivierung
  - `activation: {conditions, match, season: {from, to}}`. Conditions evaluated on refresh and whenever one of their entities changes; inactive → no reminders (open ones dropped). Season filters by event day, also across the turn of the year.
- [x] Aktionen beim Erledigen
  - `on_done`: script (parallel) with the text variables plus `person`, `via`, `reminder_id`, `titles`.
- [x] Weitere Quellen
  - `sources` accepts calendar, todo, date, datetime, input_datetime, sensor. To-dos via `todo.get_items` (needs_action, with due); others from the entity state.
- [x] Vorlagen + Export/Import
  - 4 built-in templates (de/en by server language), own templates in storage 1.3. Import is all-or-nothing and renames taken ids.
  - Translations are generated by `scripts/build_translations.py` (edit texts there, then run it).
- [x] Release v0.6.0
  - Checked in the real HA frontend with `scripts/check_card.py` (template picker, advanced step with HA person/condition/action editors). Found and fixed: the match preview validated the whole rule.
  - Note for shell use: `pkill -f` / `pgrep -f` with a pattern that appears in the own command line kill the own shell – use `pgrep -f "[b]in/hass --config"`.
  - Bundle: 31 KB gzip.

## 0.6.1 – Feedback Steven (test of 0.5.0)
- [x] Editor reset all edits regularly
  - Cause: the signal editor assigned its edits to the `signal` property passed by the rule editor; Lit re-sets object properties on every parent render (`!isPrimitive(value)` always commits), and the card re-renders the editor on every hass update → original signal restored. Rule: **child elements never write their input properties**; edit a copy in `@state` (`_sig`), emit events. `laeutwerk-field` no longer writes `value`; empty lists use a shared constant.
  - Reproduced and verified in the real frontend; `scripts/check_card.py` now types into the signal editor and posts state changes (fails if the edit is lost).
- [x] Push recipients by ticking persons instead of notify actions
  - `laeutwerk/persons` lists persons with their companion-app notify actions; signal option `only_present` for `audience: persons`. Notify actions only as optional extra field.
- [x] Release v0.6.1

## 0.6.2 – Praxistest v0.6.1 (11.11.2026, Testregel auf `calendar.rodgau_abfallkalender`)
- [x] „Nächster Termin“ zeigte einen schon verfallenen Termin
  - `RuleRunner.next_occurrence()` now skips occurrences whose reminder is done or missed, or whose expiry has passed. Occurrences made only of to-dos / intervals stay "next" until acknowledged (missed does not count for them: the item is still open and carried to today). Affects `next_event` of the state sensor, `_naechster_termin`, `get_rules` / websocket status and the card's rule list.
- [x] Automatische Mehrzahl für jede Spalte, auch wo sie unsinnig ist
  - Implemented as proposed: a column is a name (plural "<name>n", as before) or `{name, plural: false | "<own name>"}`. Both forms are read, so no storage migration; validation stores the short form while the plural is the default (`model.column_spec`), so existing rules, exports and templates are unchanged.
  - Decision for `plural: false` with bundles: the variable holds the **unique values joined with "und"** (one value if all are equal). Reason: no information is lost ("die und den" shows the mix), and with one value per bundle it reads exactly as before. With plural on, `{column}` stays the first value (unchanged).
  - Clash check only for active plurals (incl. own plural names); column names are still checked against reserved names.
  - Card: toggle under each column name in the keyword table (shows `{tonnen}` or "keine Mehrzahl"); variable chips and new signal texts only use plurals that exist. Renaming keeps the setting.
- [x] `acknowledged_by` leer, wenn der HA-Benutzer keiner Person zugeordnet ist
  - `manager.async_who(hass, context)`: person linked to the user → (name, person entity); else the user's display name (no person); nobody for system users, contexts with a parent (automations / scripts) and calls without user. Used by the button, the acknowledge action and push buttons. Tag and trigger keep `person_ref` (person of the trigger / user).
  - New reminder / history field `acknowledged_person` (person entity). The rotation "after the one who did it last" uses only that and skips entries with a user name only; history from before 0.6.2 (no field) is matched by name as before. An explicit `person` in `laeutwerk.acknowledge` may be a person name or entity id.
  - The card no longer sends the user name as `person` (that bypassed the person link).
- [x] Release v0.6.2
  - Checked in the real frontend (plural toggle in the column header, edit regression check still green).

## 0.6.3 – NFC-Tag aus einer Variable (Praxistest, Regel `claude_muell`)
- [x] `acknowledge: [{type: tag, tag_id: "{nfc}"}]`
  - Still one `tag_scanned` listener per rule. Fixed tags behave as before (acknowledge what is due). Tag ids with `{…}` are resolved **per event** of a reminder (so a bundle accepts the tag of each hit) without the automatic capital letter (`render(..., capitalize=False)`), and only reminders that are reminding / snoozed or planned within the early window (24 h) are candidates; a tag that fits none acknowledges nothing (debug log).
  - Validation: variables in `tag_id` must be keyword columns (or their active plurals) or event variables. Tags are no entities, so no repair issue.
  - Resolved tags in the status (`reminders[].tags`) and in `laeutwerk/preview` (`events[].tags`); the card shows variable chips at the tag field and the resolved tag of the next match. The editor preview only sends tag acks whose variables exist.
- [x] Release v0.6.3

## 0.7 – Usability (Stevens Auswahl, 11.11.2026: alle Vorschläge, NFC als Auswahl)
- [x] 1 Editor-Schritte einklappbar mit Zusammenfassung; neue Regeln Schritt für Schritt
  - `stepSummary()` per step; existing rules open collapsed, new rules open step 1 and offer „Weiter“ (opens the next, scrolls to it). Bodies are only rendered when open.
- [x] 2 Verständliche Fehlermeldungen (deutsch) am betroffenen Schritt, Prüfung vor dem Speichern
  - `ruleProblems()` checks in the card (name, source/interval, empty keyword, columns, time, push recipients/message, lamp, speaker+text, empty tag, season, stage); steps get a badge and open. Server errors: `errorStep()` (path / message → step) and `translateError()` (common messages → plain German), original in „Details“.
- [x] 3 „Rückgängig“ nach Erledigt
  - Service `laeutwerk.reopen` (any user, like acknowledge): done → reminded (or planned if it had not reminded yet) while not expired; history entry removed; no signals again, `on_done` actions are not undone; interval rules refresh. Card: toast „Erledigt: … · Rückgängig“ for 8 s.
- [x] 4 Ungespeicherte Änderungen: Rückfrage beim Verwerfen, Entwurf im Browser
  - „Abbrechen“ asks „Änderungen verwerfen?“ when dirty. Draft in `localStorage` (`laeutwerk-draft-<id|new>`, debounced, try/catch – per browser only), offered with „Wiederherstellen / Verwerfen“; removed on save or discard.
- [x] 5 NFC-Tag aus den in HA angelernten Tags auswählen
  - HA websocket `tag/list` (id, name): chips under the tag field and a `<datalist>` for the tag field and keyword columns named like nfc/tag.
- [x] 6 Stichwörter aus den Termintiteln des Kalenders vorschlagen
  - `laeutwerk/preview` with `titles: true`: distinct titles of the next 60 days with count and whether the keyword table matches; the card offers the unmatched ones (+ „Alle übernehmen“).
- [x] 7 Signal testen ohne vorher zu speichern
  - Websocket `laeutwerk/test_signal` (admin) with the editor's rule (saved or not) and the signal; uses the next match or a sample event.
- [x] 8 „Später“ mit Auswahl (1 h, 3 h, morgen früh)
  - `laeutwerk.snooze` accepts `until` (time of day, next occurrence; „morgen früh“ = 07:00).
- [x] 9 Details einer Erinnerung beim Antippen
  - From the reminder payload (reminded, next time, snoozed, expiry, assignee, stage, signals sent with last time, deferred, tags).
- [x] 10 Freundlichere Eingaben (Saison, Eskalation, Farbmuster)
  - Season: day + month selects. Escalation: „nach“ (number + min/h) or „um“ (time). Light with colour from column: swatches of the next matches.
- [x] 11 Rückmeldungen (Gespeichert, Gesendet) und Lade-Zustände
  - Toasts in the card (saved, done with undo, later); „…“ on busy buttons.
- [x] 12 Regeln sortieren und durchsuchen
  - Websocket `laeutwerk/rules/reorder` (admin), subscribe sends `reordered`; card „Sortieren“ mode with ↑/↓. Search field from 6 rules on.
- [x] Release v0.7.0
  - Checked in the real frontend (`scripts/check_card.py` + manual run): details, later choices, undo, collapsed editor, suggestions, problem at step 1. The check script opens the collapsed steps and waits for the fields to load.
  - Bundle: 39 KB gzip (was 31).
  - Lesson: doc edits by script must assert that the anchor exists – inserting before „## 1.0“ silently did nothing after the heading had been replaced in 0.6.2 (fixed here).

## 0.7.1 – Kompakte Karte und Erledigt-Knopf (Stevens Entscheidung, 11.11.2026)
- [x] Kompakte Karte: immer die nächste Aufgabe in einer Zeile mit Symbol
  - `tasks()`: reminding ones first (soonest `expires_at`), then planned by next reminder time; badge = number of open ones; „Keine anstehenden Aufgaben“ only if there is none. Planned tasks show just their title (it already says when).
- [x] Antippen: Fenster mit Nachfrage „Als erledigt markieren?“, „Später“, weitere Aufgaben, „+ Neue Regel“ (Admins: Vorlagen-Auswahl und Editor im Fenster)
  - `laeutwerk-task-dialog` is appended to `<body>` (fixed overlay, bottom sheet on phones), so the one-row grid cell does not clip it; the card forwards `hass` and the rules to it on every update. No undo toast in the compact card (the question is the safeguard).
- [x] Geplante Aufgaben jederzeit vorab erledigen (mit Nachfrage)
  - Acknowledge by `reminder_id` already accepts any open (also planned) reminder without the 24 h window – now covered by a test; without an id the window still applies (tags, button entity).
- [x] Großer Erledigt-Knopf in der Karte nur als Haken
  - Label (aria/title) = text of the push signal's done button, else `ack_label` of older rules, else „Erledigt“ (`doneLabel()`).
- [x] Feld „Text des Erledigt-Knopfs“ aus Schritt 5 entfernt
  - `ack_label` stays readable in stored rules / YAML; new push signals get „Erledigt“ as button text.
- [x] Release v0.7.1
  - Checked in the real frontend (compact line, dialog, confirm → done, next task follows).

## 0.7.2 – Vorab erledigte Aufgaben anzeigen (Stevens Wunsch, 11.11.2026)
- [x] Künftige, schon erledigte Aufgaben anzeigen und rückgängig machen können
  - Card, section „Erledigt“: finished today **or** done and still reopenable (`canReopen`: state done and `expires_at` in the future); today's first, then the ones done ahead by event date; ↶ button calls `laeutwerk.reopen` (no question in the big card, like the undo toast).
  - Compact dialog: section „Schon erledigt“ (`doneTasks()`); tapping asks „Diese Aufgabe wieder öffnen?“ (question instead of instant action, as decided for the compact card). Reopened tasks done ahead become planned again.
  - No backend change: reopen already worked until the expiry; done reminders of future events are kept by the engine.
- [x] Release v0.7.2

## 0.7.3 – Rückfrage beim Erledigen, Regeln aus der kompakten Karte bearbeiten (11.11.2026)
- [x] Rückfrage vor dem Erledigen (große und kompakte Karte)
  - Shared popup `laeutwerk-confirm` (`confirmAction()`, appended to `<body>`, above the task dialog, Escape/backdrop = cancel). Confirm button = the rule's done label with ✓ (e.g. „Steht draußen“). Also used for reopening: ↶ in the card's done list and „Schon erledigt“ in the dialog (replaces the dialog's reopen page). The undo toast right after „done“ in the big card stays without a question (it undoes what was just done).
  - The dialog's task page no longer asks itself; for planned tasks it notes „Noch nicht fällig – kann schon vorab erledigt werden.“, the popup asks.
- [x] Bestehende Regeln im Fenster der kompakten Karte bearbeiten
  - Section „Regeln“ (admins): all rules with ✎, opens the rule editor in the dialog; „+ Neue Regel“ below.
- [x] Release v0.7.3
  - Checked in the real frontend: cancel keeps the task open, confirm marks it done; compact popup; editor opens for a chosen rule.

## 0.7.4 – Signal-Liste mit Namen und Stufenfarben, Trennlinien (11.11.2026)
- [x] Signal-Beschriftung mit Entitätsnamen
  - `signalTitle()` / `signalTargets()`: lamps, speakers, persons (friendly names), audience words, extra notify actions, entity ids found in custom actions. The recipients moved from the summary into the title.
- [x] Signale nach Eskalationsstufe einfärben, Farben je Stufe in Schritt 7
  - Backend: optional `escalation[].color` (#rrggbb, validated). Card: `stageColor()` (stage 0 = neutral; default palette amber, red, violet, blue, green when a stage has no colour); signal row with coloured left bar, tinted icon and a „Stufe n“ chip; in step 7 the stage chip opens a colour picker.
- [x] Trennlinien in Listen
  - Shared `.divided` style: signals, ways to acknowledge, escalation stages, next matches, push recipients, quiet times; card lists (upcoming, done, rules) and the compact dialog's lists.
- [x] Release v0.7.4
  - Checked in the real frontend (steps 4, 5, 7 with staged signals).

## 0.7.5 – Quelle „Benutzerdefiniert“, Farbwähler, Stichwort-Farben, einklappbarer Signal-Editor (11.11.2026)
- [x] Notify-Aktionen aus der Push-Einstellung entfernt
  - Push-Empfänger nur noch per Personen-Häkchen. `mapTargetsToPersons()` ordnet alte `targets` beim Öffnen der Person mit diesem Handy zu (nicht bei „nur Anwesende“, da eine Notify-Aktion unabhängig von Anwesenheit ging); übrige bleiben als „Zusätzlich an … ✕“ sichtbar. Backend unverändert (`targets` bleibt gültig).
- [x] HA-eigene Farbwähler
  - `laeutwerk-field` mit `color_rgb` (ha-selector, hex ↔ rgb; Fallback `<input type=color>`). Leeres Feld zeigt „Farbe wählen“ statt Schwarz, ✕ entfernt die Farbe; `suggest` schlägt eine Farbe vor.
- [x] Schritt 1: Quelle „Kalender | Benutzerdefiniert“
  - Benutzerdefiniert = Intervall ab Erledigung. Schritt 2 entfällt dann, Nummern rücken nach; beim Speichern wird nur der Teil des gewählten Modus übernommen (`_forSaving`).
- [x] Farbe je Stichwort, in Signalen wählbar
  - Backend: `KeywordRow.color`, `color_from_keyword` am Licht-Signal, mehrere Treffer blinken abwechselnd (`light_colors` liefert eine Liste). Karte: Farbspalte in der Stichwort-Tabelle, „Farben aus Spalte übernehmen“ für eine alte `farbe`-Spalte, Licht: „Farbe des Stichworts | Feste Farbe“ mit antippbaren Stichwort-Farben.
- [x] Push zeigt Personennamen statt Notify-Namen
- [x] Signal-Editor einklappbar
  - Art / Wann / Nur wenn / Was passiert / Grenzen mit Zusammenfassung; Push zusätzlich Empfänger / Texte / Knöpfe mit Trennlinien.
- [x] Release v0.7.5
  - Im echten Frontend geprüft (Schritt 1 + 2 mit Farbwählern, Push- und Licht-Signal); `check_card.py` öffnet die Bereiche jetzt selbst.

## 0.7.6 – Eigener Farbkreis (12.11.2026)
- [x] Eigener Farbwähler `laeutwerk-color-popup` (`color-picker.ts`) statt HA-`color_rgb`-Selektor
  - Warum: HAs `ha-hs-color-picker` (Lampen-Dialog) ist intern und wird erst mit einem Lampen-Dialog geladen; der allgemeine Selektor öffnet nur den Browser-Dialog.
  - Feld: Farbfläche + Name/Hex, Antippen klappt darunter einen Bereich auf: Farbkreis (Farbton/Sättigung, Canvas, Markierung ziehbar per Pointer-Events, Tastatur), Favoriten-Kreise (feste Palette), Stichwort-Farben der Regel als Kreise, Hex-Eingabe, ✕ entfernt die Farbe. Gespeichert wird weiter `#rrggbb`.
  - Überall gleich: Regelfarbe, Stichwort-Farben, Stufenfarben, feste Lichtfarbe.
  - Als Popup auf `<body>` (wie `confirm-dialog.ts`), Abbrechen/Übernehmen; dunkle Farben behalten ihren Hex-Wert, bis man den Kreis berührt. Stichwort-Farben greifen auf eine alte `farbe`-Spalte zurück.
  - Im echten Frontend geprüft (`check_card.py` öffnet den Farbkreis an der Regelfarbe und in der Stichwort-Tabelle, tippt den Rand an → Rot). Bundle 176 307 → 185 319 Bytes (gemessen vor der kleinen Nachbesserung).
- [x] Release v0.7.6

## 0.7.7 – Logo und Icon (12.11.2026)
- [x] Stevens Icon/Logo (SVG in `docs/brand/`) als PNGs: `custom_components/laeutwerk/brand/` (icon 256/512 aus der transparenten Variante, logo/dark_logo 360×128 und 720×256) und README-Kopf `docs/brand/readme-logo-{light,dark}.png` (1440×512)
  - Gerendert mit Playwrights headless Chromium und Inter Bold (eingebettet, nicht im Repo); `laeutwerk-logo-light.svg` = Logo mit dunkler Schrift (#141417) für helle Themes.
  - Brands-Repo nimmt keine Custom Integrations mehr an (seit HA 2026.3) – lokaler `brand/`-Ordner genügt, wie bei Zeitwerk.
- [x] Release v0.7.7

## 0.8.0 – Stichwort-Icons, Überschrift, aufgeräumter Editor (12.11.2026)
- [x] Backend: `KeywordRow.icon` (flach in der Zeile wie `color`, Spalte „icon“ bleibt Spalte), `Rule.headline`/`headline_plural`; Payloads `headline` + `badges` [{icon, color}] je Treffer; Sensor-Attribut `headline`; Müll-Vorlage mit Icons
- [x] Karte: Badges mit Rückfall je Feld (Icon/Farbe des Stichworts, sonst der Regel) in Übersicht, Demnächst, Erledigt, Kompakt, Editor-Vorschau; bis zu 3 Badges bei Bündeln; Farbpunkte entfallen
- [x] Überschrift-Felder in Schritt 6 mit Live-Vorschau
- [x] Stichwort-Tabelle neu: runder Icon-Knopf öffnet `laeutwerk-keyword-look` (Icon, Farbe, Stichwort löschen), Spaltenkopf kompakt mit „n“-Mehrzahl-Schalter, Fade am rechten Rand
  - Erkenntnis: rechts angeheftetes × verdeckte die Variablenspalten bei 390 px → Löschen ins Fenster verlegt.
- [x] Angelernte Tag-Chips und Variablen-Chips entfernt → `laeutwerk-suggest` (Vorschläge beim Tippen: `{` → Variablen, NFC → bekannte Tags)
- [x] `laeutwerk-help-tip` („?“, Hover/Fokus/Antippen) statt Hinweistexten; fehlende Erklärungen ergänzt (de/en)
- [x] Social-Preview-Bild (`docs/brand/social-preview.png`) – muss Steven in den Repo-Einstellungen hochladen
- [x] Im echten Frontend geprüft (`check_card.py`: Stichwort-Tabelle, Icon/Farb-Fenster, Farbkreis darüber, „?“-Blase, Vorschlagsliste `{w` → `{wann}`); `check_card.py` meldet sich ohne gespeicherte Tokens mit dem Dev-Benutzer an
  - Bundle 185 443 → 210 248 Bytes (ungezippt, gemessen).
- [x] Release v0.8.0

## 0.8.1 – Fixes nach Stevens Test (12.11.2026)
- [x] „?“-Blase als Element auf `<body>` (z-index 1010) – lag in der Stichwort-Tabelle hinter den Zeilen (Stapelkontext der sticky Spalte)
- [x] Trennstrich rechts an der fixierten Stichwort-Spalte
- [x] Überschrift: Felder „ein Treffer“ / „mehrere Treffer“, Vorschau je Feld darunter; `laeutwerk/preview` liefert `plural_sample` (erfundenes Bündel aus den ersten zwei Nicht-Regex-Stichwörtern, morgen) – `None` ohne Bündeln / < 2 Stichwörter
- [x] `check_card.py`: prüft per `elementFromPoint`, dass die Blase oben liegt; `shot(full=False)` für Popups, die sich beim Größenändern schließen
- [x] Zuständigkeit Steven erklärt: wirkt nur auf Push mit Empfänger „Zuständige“, `{zustaendig}` und Statistik; fest angehakte Personen bekommen den Push immer, quittieren darf jeder
- [x] Release v0.8.1

## 0.9.0 – Stevens Sammelliste (go 12.11.2026)
Schnittstellen (fest, Backend und Karte arbeiten parallel dagegen):
- `assignee`: `{persons, rotation, substitute?: person.x, substitute_when?: {entity_id, state}}`; Vertretung wird beim Erinnern geprüft → `reminder.assignee` = Vertretung, `reminder.substitute_for` = ursprüngliche Person; Payload `assignee_name`, `substitute_for_name`
- `laeutwerk/persons`: nur Personen mit Mobile-App-Gerät
- `lookahead_days`: int 1–365, Standard 14, ≥ früheste Erinnerung + 1 Tag
- Quelle Auslöser: `start_triggers` (Trigger-Liste wie Automationen); genau eine Quelle: `sources` | `start_triggers` | `interval`; Erinnerung sofort beim Auslösen, keine zweite solange eine offen ist; `expire` zusätzlich `+<dauer>` (nach Start), Standard bei Auslöser `+12h`; Dienst `laeutwerk.start`
- `visible`: bool, Standard true (false = nicht in der Übersicht)
- `confirm`: `{message, clear_after (s, Standard 10)} | null` – Bestätigung an die erledigende Person, sonst Zuständige; `on_done`-Variablen `person_entity`, `zustaendig_entity`
- Haushalts-Ruhezeit: Integrations-Optionen `quiet` (Liste wie beim Signal); WebSocket `laeutwerk/settings` → `{quiet}`
- `sensor.laeutwerk_offen`: Anzahl offener Erinnerungen, Attribut `reminders` [{rule_id, rule_name, headline, assignee_name, since}]

- [x] 1 Zuständigkeit mit Vertretung
- [x] 2 Nur Personen mit Companion App
- [x] 3 Bereiche je Schritt mit Trennstrich
- [x] 4 Abstand der „?“ einheitlich
- [x] 5 Vorausschauen (Tage) je Regel
- [x] 6 Quellen Kalender · Auslöser · Intervall
- [x] 7 Wiederholen: einmal · wiederholen
- [x] 8 Regel in der Übersicht ausblenden
- [x] 9 Bestätigung beim Erledigen
- [x] 10 Haushalts-Ruhezeit
- [x] 11 Wiederholte Pushs ersetzen (prüfen: `tag` je Erinnerung existiert)
- [x] 12 Gesamtsensor offene Erinnerungen
- [x] 13 README komplett (docs-writer)
- [x] 14 Code-Prüfung, Editor nachladen, Kalender-Abfragen bündeln, Altlasten raus (keine Rücksicht auf alte Regeln – Stevens Vorgabe)
Erkenntnisse:
- Backend schickt `start_triggers: []` bei jeder Regel → Karte darf nur `start_triggers?.length` als Auslöser werten (war ein Fehler, im echten Frontend gefunden).
- 11: Pushs einer Erinnerung haben schon dasselbe `tag` (`notification_tag(reminder.id)`), Wiederholungen/Stufen ersetzen sich, Erledigt/Verpasst löscht sie – nichts zu tun.
- 12: `sensor.laeutwerk_offen` zählt nur „erinnert“ (wartet auf Quittung), keine geplanten/verschobenen.
- 14: Kalender-Zwischenspeicher bewusst nicht gebaut (Regeln aktualisieren zu eigenen Zeiten mit eigenen Fenstern → selten Treffer). Karte in Chunks: `laeutwerk-card.js` (Stub) + `chunk-laeutwerk-card` 96 954 B (31 686 B gzip -9), `chunk-editors` 100 778 B (22 503), `chunk-help-tip` 16 358 B (5 519), `chunk-card-editor-entry` 4 623 B (1 742); vorher 221 231 B in einer Datei. Ganzer `frontend/`-Ordner als statischer Pfad.
- Testinstanz hat keine Person mit Companion App → Zuständig/Vertretung zeigen dort nur den Hinweis; mit echter App nicht gesichtet.
- [x] Release v0.9.0
- [x] v0.9.1: hassfest-Fehler in Dienstbeschreibungen (`<duration>`, `{entity_id, state}`) – Erkenntnis: nach jedem Push auf die CI warten, nicht nur nach Tags

## 0.9.2 – Vorzeitig erledigen, Rückmeldung, ein Schritt offen (12.11.2026)
Schnittstelle:
- Regel `early`: `{mode: "off" | "hours" | "always", hours: int 1–720}`, Standard `{mode: "hours", hours: 24}`; gilt für alle Quittierwege (Push-Knopf, Karte, Tag, Trigger, Dienst). Das alte `early` je Trigger-Quittierung entfällt. Bei Auslöser-Regeln ohne Bedeutung.
- Regel `early_feedback`: `{message, clear_after (s, Standard 10)} | null` – zu früher Versuch → kurze Push an die Person (sonst Zuständige), Variablen des nächsten passenden Termins (bei Tag: Termin dieses Tags).
- `laeutwerk/acknowledge` (WS) bzw. Dienst-Antwort: zusätzlich `too_early: str | null` (gerenderter Text) → Karte zeigt kurze Meldung.
- Editor: immer nur ein Schritt offen; Texte kürzen, eindeutig bleiben.
- [x] Backend
- [x] Karte
- Erkenntnis: Standardtext ohne ({datum}) – {wann} ist ab einer Woche schon das Datum („am 24.11.“), sonst doppelt. Segment „Vorher“ + Feld „Stunden vor der Erinnerung“ (vorher „Bis … Std. vorher“, brach um und stand doppelt).
- Im echten Frontend geprüft: Quittieren 12 Tage vorher → `acknowledged: []`, `too_early: "Rest ist erst am 24.11. dran."`; Schritt 5 antippen → genau 1 Schritt offen.
- [x] Release v0.9.2

## 1.0 – Veröffentlichung
- [ ] README mit Screenshots (hell + dunkel), vollständige Doku
- [x] Logo/Brand-Assets (Steven fragen) – geliefert 12.11.2026, in 0.7.7 eingebaut
- [ ] HACS-Standardliste (vorher Steven fragen)
- [ ] Release v1.0.0
