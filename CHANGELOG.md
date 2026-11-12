# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.11.4] - 2026-11-12

### Fixed
- Headlines with `{seit}` / `{seit_min}` now count up live in the card
  (overview, compact card, dialog) instead of showing the waiting time of the
  last reminder pass. Computed in the browser, no extra server traffic; the
  card ticks every 15 s.

## [0.11.3] - 2026-11-12

### Changed
- Compact card: one line per open task (icon, title, status) instead of only
  the first one with a counter; the card grows with the number of open tasks.
  Tapping a line opens the dialog on that task.

### Fixed
- Compact card dialog: other open tasks show their status ("erinnert 19:42")
  instead of the label "Offene Aufgaben".

## [0.11.2] - 2026-11-12

### Fixed
- Trigger, condition and action editors showed only "+" and an add dialog
  without most texts on dashboards, unless the Settings panel had been opened
  before: Läutwerk now loads Home Assistant's automation editor texts itself.

### Changed
- Escalation stages: the separate colour row is gone; tap the stage button
  ("Stufe 1") to pick its colour.

## [0.11.1] - 2026-11-12

### Added
- Compact card dialog: on/off switch next to every rule.

### Fixed
- Compact card dialog: reminders show the keyword icon in its colour (like
  the big card) instead of the rule icon.

### Changed
- Help for "Kommt bei": every reminder is a pass (first, repeat, "later",
  stage); "from 2nd" covers all after the first.

## [0.11.0] - 2026-11-12

### Changed
- `send_on` replaces the signal settings `stage` and `every_stage`, and the
  per-signal `limit` on "immediately" signals. Values: `all` (default), `first`,
  `repeat`, `stage` (with `stage: N`, plus `stage_repeat: true` for every later
  reminder).
- `limit` applies only to "on opportunity" signals.

### Added
- `expire: "never"` for trigger rules: a new trigger while a reminder is open
  marks it missed and starts a fresh one.

### Removed
- Plural text fields: `title_plural`, `message_plural`, `text_plural`,
  `headline_plural`.
- Repeat texts: `title_repeat`, `message_repeat`, `text_repeat`.
- `every_stage`, `plural_sample`.

### Migration
- Stored rules are converted automatically on the first start: plural and
  repeat texts are dropped, `stage` → `send_on: stage`, `limit: 1` →
  `send_on: first`.

## [0.10.1] - 2026-11-12

### Fixed
- Compact card: the rule editor in its dialog showed no source picker (only
  the label "Quellen") and an incomplete trigger editor. Dialogs and popups
  were attached outside Home Assistant's element tree, where its pickers do
  not get their data; they now live inside it.
- Trigger rules: the collapsed steps no longer show calendar-only details
  ("Vortag 17:00", "gebündelt").

## [0.10.0] - 2026-11-12

### Added
- Time variables in texts: `{seit}`, `{seit_min}`, `{erinnert_um}`, `{nr}`.
- Repeat texts (`title_repeat` / `message_repeat` / `text_repeat`), used from
  the 2nd reminder on.
- `every_stage: true` for signals: sent at the first reminder and at every
  escalation stage.
- `on_missed` and `on_reminded` actions next to `on_done`.
- `min_age` for escalation stages.
- Sensor attributes `reminded_at`, `last_reminded_at`, `repeats`, `finished_at`.
- Sensor `sensor.laeutwerk_<rule>_wartet_seit` (disabled by default).

### Changed
- "at HH:MM" escalation stages are the next occurrence after the first
  reminder; before, a trigger rule fired such a stage at once.
- "+ Rule" button in the rules section; the "+" in the card header is removed.
- Help bubbles are shown in the top layer, so they also work inside dialogs.

## [0.9.2] - 2026-11-12

### Added
- `early` rule setting (`off` / `hours` / `always`) for every way of
  acknowledging, replacing the fixed 24 h window.
- `early_feedback`: a too-early attempt sends a short push with the next date,
  removed again after `clear_after` seconds.
- `too_early` in the `laeutwerk.acknowledge` response and as a message in the card.

### Changed
- The rule editor opens one step at a time; shorter help texts.
- The fixed 24 h window and the per-trigger `early` flag are replaced by the
  rule setting.
- Explicitly acknowledging a planned reminder by id now follows the rule setting.

## [0.9.1] - 2026-11-12

### Fixed
- Service description of `create_rule` / `update_rule` contained `<…>` and
  `{…, …}`, which Home Assistant treats as HTML / placeholders (hassfest
  failed, the description could show garbled in the action editor).

## [0.9.0] - 2026-11-12

### Added
- Substitute for the responsible person (`assignee.substitute` with
  `substitute_when: {entity_id, state}`): takes over at reminder time when the
  entity has the given state; `{zustaendig}`, the push audience and the
  statistics follow it, the card shows "Alida (substitute for Steven)".
- Only persons with the companion app are offered anywhere in Läutwerk.
- Trigger source: `start_triggers` starts a reminder from any Home Assistant
  trigger; no second reminder while one is open. Action `laeutwerk.start`
  starts one from an automation. `expire` accepts `+<duration>` (default
  `+12h` for trigger rules).
- `lookahead_days` per rule (default 14); checked against the earliest
  reminder time on save.
- `visible: false` hides a rule from the card overview.
- Confirmation (`confirm: {message, clear_after}`): short push to whoever
  acknowledged (else the responsible person), removed after `clear_after`
  seconds (default 10). `on_done` actions also get `person_entity` and
  `zustaendig_entity`.
- Household quiet time in the integration options (one window, skip or
  defer), used by every signal without its own quiet time; `laeutwerk/settings`
  WebSocket command.
- Sensor `sensor.laeutwerk_offen`: reminders waiting for acknowledgement over
  all rules, attribute `reminders`.

### Changed
- Step 1 of the editor is "Source" with Calendar · Trigger · Interval.
- Repeat is "once" or "repeat" (every N minutes, default 60, at most M times,
  default 24).
- Repeated pushes of a reminder replace each other (same tag) and are removed
  when the reminder is done or missed.
- Features within an editor step are separated by thin dividers; help icons
  ("?") are consistent across the editor.
- The editors load lazily: the overview needs 31.7 KB gzipped (96,954 bytes)
  instead of the whole 221 KB card; the editors (22.5 KB + 5.5 KB gzipped) and
  the visual card editor (1.7 KB gzipped) load when opened.

### Removed
- Keyword colours from `farbe` / `color` columns and the button that took
  them over; only a keyword's own `color` / `icon` is used. `colors` in
  payloads is gone.
- Compatibility code for rules and history from before 0.9. Older rules may
  need to be saved again in the editor.

## [0.8.1] - 2026-11-12

### Fixed
- Help bubbles ("?") are drawn on top of everything; in the keyword table
  they were covered by the table rows.
- Thin divider between the fixed keyword column and the scrolling columns.

### Changed
- Headline fields are labelled "one match" / "several matches", each with its
  own preview directly below. The plural preview uses a real bundle or a
  made-up one from the first two keywords (`plural_sample` in
  `laeutwerk/preview`); an empty plural field shows the singular text.

## [0.8.0] - 2026-11-12

### Added
- Own icon per keyword (`icon` in the keyword row, next to its colour). The
  card (overview, upcoming, done, compact, editor preview) shows the icon of
  the due keyword tinted in its colour; bundles show up to three badges. Icon
  and colour fall back to the rule's icon / colour independently.
- Editable headline per rule (`headline`, `headline_plural`, with variables),
  e.g. "{wann} raus: {tonnen}"; also the `headline` attribute of the rule
  sensor. Reminder payloads carry `headline` and `badges`.
- Help behind small "?" icons (hover, focus or tap) in the rule, signal and
  card editors, with new explanations for every step.
- Suggestions while typing: `{` offers the available variables in all text
  fields (signal texts, headline, tag ids), NFC tag fields offer the tags
  Home Assistant knows.
- GitHub social preview image.

### Changed
- Keyword table redesigned: compact header, fixed keyword column with a round
  icon button (icon, colour, delete keyword), plural toggle in the column
  header, fade at the right edge while more columns follow.
- Removed the known-tag chips and the variable chips (replaced by the
  suggestions).
- Built-in "Müll" template comes with keyword icons.

## [0.7.7] - 2026-11-12

### Added
- Brand icon and logo (by Steven Glab): shipped in
  `custom_components/laeutwerk/brand/` (Home Assistant shows the local
  branding of custom integrations) and as README header (light and dark).

## [0.7.6] - 2026-11-12

### Changed
- Own colour picker for all colour fields (rule, keywords, escalation stages,
  fixed light colour): a hue/saturation wheel with a draggable marker,
  favourite colours, the rule's keyword colours, a hex field and "Remove
  colour". It opens as a popup, so it is not clipped by the keyword table, and
  no longer depends on Home Assistant's internal elements or the browser's
  colour dialog. Keyword colours from an older colour-name column are offered
  too.

## [0.7.5] - 2026-11-11

### Added
- Every keyword can have its own colour (`color` in the keyword row, colour
  picker in step 2). Light signals can blink in the colours of the matched
  keywords (`color_from_keyword`, alternating when several match).
- Step 1 offers the source *Calendar* or *Custom* (recurring after it was
  last done, the interval).
- "Take colours from column" turns an older colour-name column into keyword
  colours.

### Changed
- Colours are picked with Home Assistant's colour picker; an empty colour
  shows "Choose a colour" instead of black and can be removed again.
- The signal editor is split into collapsible sections with a summary; push
  signals into recipients, texts and buttons.
- Push recipients are only chosen by ticking persons. Older notify actions of
  a person's phone are shown as that person; others stay listed and can be
  removed. Push signals are labelled with person names.

## [0.7.4] - 2026-11-11

### Added
- Escalation stages can have a colour (`escalation[].color`, picker in step 7);
  signals of a stage are marked in that colour in the signal list.

### Changed
- The signal list names what each signal reaches ("Light · Stehleuchte",
  "Push · Steven, Anna").
- Lists in the editor, the card and the compact dialog have thin dividers.

## [0.7.3] - 2026-11-11

### Added
- Confirmation before marking a task as done – in the card and in the
  compact card's dialog – and before reopening one.
- The compact card's dialog lists the rules for editing (administrators).

## [0.7.2] - 2026-11-11

### Added
- Tasks done ahead of their event stay visible and can be undone until they
  expire: in the card under *Done* (↶ button), in the compact card's dialog
  under *Done already* (with a confirmation).

## [0.7.1] - 2026-11-11

### Changed
- Compact card: always the next task in one line (open ones first, the one
  that expires first on top, then planned ones) with the rule's icon and the
  number of open tasks – no more "all done" line. Tapping opens a dialog to
  confirm *done* (also ahead of time for planned tasks), snooze, pick another
  task or create a new rule.
- The done button of open reminders in the card is a check mark only; its
  label comes from the push signal's done button.
- The rule editor no longer has the "text of the done button" field
  (`ack_label` in existing rules is still read).

## [0.7.0] - 2026-11-11

### Added
- Undo after *Done* in the card; action `laeutwerk.reopen`.
- *Later* with choices (1 hour, 3 hours, tomorrow morning); `laeutwerk.snooze`
  accepts `until` (time of day).
- Details of a reminder when tapped (reminded, next time, expiry, signals
  sent, held back, responsible person, stage, tags).
- Keyword suggestions from the event titles of the calendar (`laeutwerk/preview`
  with `titles`).
- NFC tags can be picked from the tags Home Assistant knows.
- Signals can be tested before the rule is saved (`laeutwerk/test_signal`).
- Rules can be sorted (`laeutwerk/rules/reorder`) and searched.
- Feedback messages (saved, done, later) and busy states.

### Changed
- Rule editor: steps are collapsed with a summary; new rules are filled in
  step by step. Problems are checked before saving and shown at their step in
  plain words (server messages translated, original under "Details").
- Unsaved changes need a confirmation and are kept as a draft in the browser.
- Friendlier inputs for season (day and month) and escalation stages (after
  minutes / hours or at a time of day); colour swatches for light signals.

## [0.6.3] - 2026-11-11

### Added
- NFC tag ids may use variables of the keyword table
  (`acknowledge: [{type: tag, tag_id: "{nfc}"}]`): only the tag of the bin
  that is due acknowledges; a bundle accepts the tag of each of its hits.
  Fixed and variable tags can be mixed. The card offers the variables as chips
  at the tag field and shows the resolved tag of the next match.

## [0.6.2] - 2026-11-11

### Added
- Plural per keyword column can be switched off (`{name: artikel, plural:
  false}`, toggle in the column header of the card) or given an own name
  (`{name: tonne, plural: tonnen_liste}`). Without plural, a bundle's
  variable holds the different values joined with "und". Plain column names
  work as before.

### Fixed
- "Next event" (sensor `…_naechster_termin`, attribute `next_event`,
  `get_rules`, card) no longer shows an event whose reminder has expired, is
  done or missed – e.g. today's all-day collection after `event_day 12:00`.
  Overdue to-dos and intervals stay the next event until acknowledged.
- "Acknowledged by" stayed empty when the Home Assistant user has no person:
  it now falls back to the user's display name (system users, automations
  and scripts stay empty). The person entity is stored as
  `acknowledged_person`; the rotation "after the one who did it last" only
  counts acknowledgements by a person.

## [0.6.1] - 2026-11-11

### Fixed
- Card: edits in the signal editor were reset to the previous values on
  every Home Assistant state change, so signals could hardly be edited.

### Changed
- Push recipients: tick persons in the signal editor (their companion app
  phones get the push; persons without the app are flagged), optionally
  "only who is at home". Notify actions moved to an optional field for other
  devices. New signal option `only_present` for `audience: persons`.

### Added
- Websocket `laeutwerk/persons` (persons with their notify actions).

## [0.6.0] - 2026-11-11

### Added
- More sources: to-do lists (open items with a due date), date, datetime and
  date helper entities, timestamp / date sensors. Overdue to-dos remind daily.
- Interval since done (`interval`): due again n days after the last
  acknowledgement, daily until done when overdue.
- Activation (`activation`): rule only active under conditions (all / any)
  and in a season.
- Actions when done (`on_done`).
- Responsibility (`assignee`) with rotation (fixed, weekly, per event, after
  the one who did it last), `{zustaendig}`, push audience `assignee`,
  statistics.
- Escalation stages (`escalation`, signal `stage`).
- Templates: built-in ones, own templates, YAML export / import (card,
  websocket, actions `export_rules` / `import_rules`).
- Card: template picker, "Advanced" step, sources and interval in step 1,
  export and "save as template", signal stage, responsible person on open
  reminders, "inactive" rules.

### Changed
- Storage version 1.3 (own templates; older data is migrated).
- `sources` may be empty when the rule has an `interval`.

### Fixed
- The editor's match preview no longer fails because of half-filled
  fields in other steps.

## [0.5.0] - 2026-11-11

### Added
- History of finished reminders per rule (who, how, when or missed), shown
  in the card's single rule view; websocket `laeutwerk/history`.
- Visual card editor (view, rule / rules filter, sections, compact).
- Repair issues for rules that refer to missing entities or notify actions.
- Diagnostics download for the integration and per rule device.

### Changed
- Storage version 1.2 (adds the history; older data is migrated).

### Fixed
- Announcement test no longer imports the optional TTS component (CI).

## [0.4.0] - 2026-11-11

### Added
- Card `custom:laeutwerk-card`: "today & upcoming" overview with open,
  upcoming and finished reminders, *Later* and done buttons, colour dots,
  empty state, rule list with on/off switches; single rule view; compact line.
- Rule editor in the card: calendar, keyword table with free columns
  (horizontally scrollable), live preview, reminder times, repeat, signals,
  ways to acknowledge, bundling, expiry.
- Signal editor with Home Assistant's trigger, condition and action editors,
  variable chips, text preview, limits, quiet times, test and YAML view.
- Websocket API `laeutwerk/rules/list|get|create|update|duplicate|delete|subscribe`
  and `laeutwerk/preview` (also for unsaved rules).

## [0.3.0] - 2026-11-11

### Added
- Signals "on opportunity": any Home Assistant trigger, active only while a
  reminder is open; `manual_only` ignores automations and scripts; `{person}`.
- Repeat while a reminder is open (`repeat: {every, max}`).
- Snooze: action `laeutwerk.snooze` and push button `{snooze: 3h, label: …}`.
- Acknowledge by NFC tag (`tag_scanned`) or any trigger (door contact, zone,
  button).

## [0.2.0] - 2026-11-11

### Added
- Light signal (blink / pulse, colour fixed or from a keyword column, previous
  state restored), announcement (TTS with `announce`, volume, singular /
  plural text) and custom action (any Home Assistant actions with the text
  variables).
- Per signal: "only if" conditions (all / any), quiet times (skip or send when
  the quiet time ends) and frequency limits (per reminder, minimum interval).
- Push audience: all persons, persons at home or selected persons.
- Action `laeutwerk.test_signal` for saved and unsaved signals.

## [0.1.0] - 2026-11-11

### Added
- Rules: calendar sources, keyword table with free columns (contains / starts
  with / regex), all-day filter, several reminder times relative to the event,
  bundling of events of the same day, expiry.
- Reminder lifecycle planned → reminded → done / missed, restart safe; every
  reminder time is sent exactly once.
- Text variables incl. automatic plural (`{tonne}` / `{tonnen}`) and
  singular / plural texts.
- Push signal (notify actions) with an acknowledge button; the notification is
  cleared when the reminder is done or missed.
- Entities per rule (state, open, next event, done button, switch), actions
  (`acknowledge`, `trigger`, `get_rules`, `create_rule`, `update_rule`,
  `delete_rule`, `duplicate_rule`, `enable`, `disable`) and bus events.
