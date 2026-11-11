# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
