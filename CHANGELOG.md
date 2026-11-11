# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
