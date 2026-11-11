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
- [ ] Model, Store mit Migrationen, Config-Flow (Single Instance)
- [ ] Kalender lesen (`calendar.get_events`, 14 Tage voraus, alle 15 min und bei Änderung), Filter, Stichwort-Tabelle, Variablen inkl. Mehrzahl
- [ ] Erinnerungs-Lebenszyklus (B5), Zeitpunkte als Timer, Bündeln, Verfallen, Neustart-fest
- [ ] Signal Push (sofort), Quittieren per Knopf, Dienst, Push-Aktion
- [ ] Entitäten, Dienste (inkl. `get_rules`), Ereignisse
- [ ] Tests inkl. Sommer-/Winterzeit; Release v0.1.0

## 0.2 – Signale
- [ ] Licht-Signal (Muster, Farbe aus Spalte, Zustand wiederherstellen), Ansage (TTS announce, Lautstärke, Einzahl/Mehrzahl-Text), eigene Aktion
- [ ] Ruhezeiten (auslassen/nachholen), Zielgruppe, Häufigkeit
- [ ] `test_signal`; Release v0.2.0

## 0.3 – Gelegenheiten und Quittierung
- [ ] „Bei Gelegenheit“ mit beliebigem HA-Trigger, Zeitfenster, `manual_only` über `context`, `{person}`
- [ ] Wiederholen, Snooze
- [ ] Quittierung per NFC-Tag, Türkontakt, Zone, Taster
- [ ] Release v0.3.0

## 0.4 – Karte
- [ ] Ansicht „Heute & demnächst“ inkl. Leerzustand, Live-Updates
- [ ] Regel-Editor mit Stichwort-Tabelle (horizontal scrollbar), Vorschau (`laeutwerk/preview`), Signal-Liste
- [ ] Signal-Editor mit HA-Trigger-/Bedingungs-/Aktions-Editor, YAML-Ansicht
- [ ] Release v0.4.0 → Steven kann die Müll-Regel parallel zur bestehenden Automation testen

## 0.5 – Feinschliff
- [ ] Verlauf je Regel, Kompakt-Modus, visueller Karteneditor
- [ ] Übersetzungen de/en vollständig, Reparaturen, Diagnose
- [ ] Release v0.5.0

## 0.6 – Erweiterungen (B7)
- [ ] Intervall ab Erledigung
- [ ] Eskalationsstufen
- [ ] Zuständigkeit und Wechsel
- [ ] Aktivierung
- [ ] Aktionen beim Erledigen
- [ ] Weitere Quellen
- [ ] Vorlagen + Export/Import
- [ ] Release v0.6.0

## 1.0 – Veröffentlichung
- [ ] README mit Screenshots (hell + dunkel), vollständige Doku
- [ ] Logo/Brand-Assets (Steven fragen)
- [ ] HACS-Standardliste (vorher Steven fragen)
- [ ] Release v1.0.0
