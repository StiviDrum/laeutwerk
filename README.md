# Läutwerk

Reminders for Home Assistant that turn **calendar events** into signals which
stay active **until someone acknowledges them**.

> **Status:** early development. 0.1 contains the core (rules, reminders, push
> signal, entities, services); the card to edit rules follows in 0.4 – until
> then rules are created with the `laeutwerk.create_rule` action. See
> [docs/TASKS.md](docs/TASKS.md) for progress.

A *rule* describes an occasion: which calendar, which events (keyword table),
when to remind, which signals (push, light, announcement, any Home Assistant
action), when not to disturb and how "done" is recognised (push button, NFC
tag, door contact, zone, dashboard, service). Every matching event becomes a
*reminder* with its own state that stays open until it is acknowledged or
expires.

Läutwerk does not fetch events itself. Waste Collection Schedule, Google
Calendar, CalDAV or the local Home Assistant calendar remain the sources;
Läutwerk is the layer between "the event is in the calendar" and "somebody
has done it".

Läutwerk ships its own Lovelace card (`custom:laeutwerk-card`), which registers
itself – no manual resource needed. Sibling project:
[Zeitwerk](https://github.com/StiviDrum/zeitwerk).

## Installation (HACS, custom repository)

Requires Home Assistant 2026.11 or newer.

1. HACS → ⋮ → *Custom repositories* → `https://github.com/StiviDrum/laeutwerk`, type **Integration**.
2. Install **Läutwerk**, restart Home Assistant.
3. *Settings → Devices & services → Add integration → Läutwerk*.

## How it works

A reminder goes through these states: **planned** (event found) → **reminded**
(reminder time reached, signals sent) → **done** (acknowledged) or **missed**
(expired without acknowledgement). Signals are sent exactly once per reminder
time, also across restarts; a reminder time missed while Home Assistant was
off is caught up once.

Calendars are read with `calendar.get_events` (14 days ahead, every 15 minutes
and when a calendar changes).

### Example rule

*Developer tools → Actions → `laeutwerk.create_rule`*:

```yaml
action: laeutwerk.create_rule
data:
  config:
    id: muell
    name: Müll rausstellen
    sources: [calendar.abfallkalender]
    filter:
      all_day: true
      keywords:
        columns: [tonne, farbe]
        rows:
          - {match: Papier, tonne: Papiertonne, farbe: blau}
          - {match: Bio, tonne: Biotonne, farbe: grün}
    reminders:
      - at: "-1d 17:00"
    signals:
      - type: notify
        targets: [notify.mobile_app_my_phone]
        title: "{wann}: {tonnen}"
        message: "Bitte heute Abend rausstellen."
        actions:
          - {ack: true, label: "Steht draußen"}
    bundle: true
    expire: "event_day 12:00"
```

- **Keyword table:** an event matches when its title contains a keyword
  (`mode: contains`, default), starts with it (`startswith`) or matches a
  regular expression (`regex`). Without rows every event matches. Every column
  becomes a text variable.
- **Times** (`reminders[].at`, `expire`): `-1d 17:00` (the day before at
  17:00), `09:00` or `event_day 09:00` (on the event day), `-2h` / `-30m` /
  `-7d` (before the start), and for `expire` also `event_start` / `event_end`
  (default).
- **Bundling:** events of the same rule on the same day become one reminder;
  one acknowledgement finishes all of them.
- **Variables** in texts: `{titel}`, `{rest}` (title without the keyword),
  `{beschreibung}`, `{ort}`, `{kalender}`, `{wann}` (heute / morgen / am
  Donnerstag – English wording if Home Assistant is not set to German),
  `{datum}`, `{uhrzeit}`, plus one per column and its plural with an appended
  `n`: `{tonnen}` = "Papiertonne und Biotonne". `title_plural` /
  `message_plural` are used when several keywords matched.
- **Acknowledge:** the button in the push notification, the entity
  `button.laeutwerk_<rule>_erledigt` or the action `laeutwerk.acknowledge`.
  A reminder can be acknowledged up to 24 h before its first reminder time.

### Entities (one device per rule)

| Entity | State |
|---|---|
| `sensor.laeutwerk_<rule>` | `planned` / `reminded` / `done` / `missed` / `inactive`, attributes with the event and its variables |
| `binary_sensor.laeutwerk_<rule>_offen` | on while a reminder waits to be acknowledged |
| `sensor.laeutwerk_<rule>_naechster_termin` | start of the next matching event |
| `button.laeutwerk_<rule>_erledigt` | acknowledge |
| `switch.laeutwerk_<rule>` | rule on/off |

### Actions and events

`laeutwerk.acknowledge`, `trigger`, `get_rules`, `create_rule`, `update_rule`,
`delete_rule`, `duplicate_rule`, `enable`, `disable`. Editing actions need an
admin (calls from automations are allowed).

Events on the bus: `laeutwerk_reminded`, `laeutwerk_signal_sent`,
`laeutwerk_acknowledged`, `laeutwerk_missed` (data: `rule_id`, `reminder_id`,
`titles`, `variables`, …).

## Development

Requires Python ≥ 3.14.2 and Node ≥ 20 (WSL2/Linux).

```bash
scripts/setup      # .venv + npm dependencies
scripts/develop    # local Home Assistant on http://localhost:8123 using ./config
scripts/lint       # ruff + eslint + prettier
scripts/test       # pytest + vitest
```

The dev instance comes with two seeded local calendars ("Abfallkalender",
"Kult61") and helper stand-ins for presence, the front door and a lamp.

## License

MIT © Steven Glab

---

# Läutwerk (Deutsch)

Erinnerungen für Home Assistant: aus **Kalenderterminen** werden Signale, die
so lange aktiv bleiben, **bis jemand sie quittiert**.

> **Status:** frühe Entwicklung. 0.1 enthält den Kern (Regeln, Erinnerungen,
> Push-Signal, Entitäten, Dienste); die Karte zum Bearbeiten folgt mit 0.4 –
> bis dahin legst du Regeln mit der Aktion `laeutwerk.create_rule` an (Beispiel
> oben). Fortschritt siehe [docs/TASKS.md](docs/TASKS.md).

Eine *Regel* beschreibt einen Anlass: welcher Kalender, welche Termine
(Stichwort-Tabelle), wann erinnern, welche Signale (Push, Licht, Ansage,
beliebige Home-Assistant-Aktion), wann nicht stören und woran man „erledigt“
erkennt (Push-Knopf, NFC-Tag, Türkontakt, Zone, Dashboard, Dienst). Jeder
passende Termin wird zu einer *Erinnerung* mit eigenem Zustand, die offen
bleibt, bis sie quittiert wird oder verfällt.

Läutwerk holt keine Termine selbst – Waste Collection Schedule,
Google-Kalender, CalDAV oder der lokale HA-Kalender bleiben die Quellen.

## Installation (HACS, benutzerdefiniertes Repository)

Benötigt Home Assistant 2026.11 oder neuer.

1. HACS → ⋮ → *Benutzerdefinierte Repositories* → `https://github.com/StiviDrum/laeutwerk`, Typ **Integration**.
2. **Läutwerk** installieren, Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → Läutwerk*.
