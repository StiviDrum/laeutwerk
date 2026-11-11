# Läutwerk

Reminders for Home Assistant that turn **calendar events** into signals which
stay active **until someone acknowledges them**.

> **Status:** early development. 0.6 contains all planned features (engine,
> card with rule editor, templates, escalation, responsibility …); 1.0 follows
> after real-world testing; rules can also be created with the
> `laeutwerk.create_rule` action. See
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
- **Plural per column:** where a plural makes no sense (e.g. `artikel`),
  switch it off in the column header of the card or write the column as
  `{name: artikel, plural: false}`. Then there is no `{artikeln}`, and with
  several matches `{artikel}` contains the different values joined with
  "und" ("die", or "die und den"). An own plural name:
  `{name: tonne, plural: tonnen_liste}`. Plain names keep the default plural.
- **Acknowledge:** the button in the push notification, the entity
  `button.laeutwerk_<rule>_erledigt`, the action `laeutwerk.acknowledge`, an
  NFC tag or any trigger (see below).
  A reminder can be acknowledged up to 24 h before its first reminder time.

### Signals

A rule can have any number of signals. Every signal has a type, optional
"only if" conditions, quiet times and a frequency limit:

```yaml
signals:
  - id: push
    type: notify
    audience: persons            # all | present | persons | assignee
    persons: [person.steven, person.anna]   # their phones (companion app)
    only_present: true           # only those of them who are at home
    targets: [notify.alexa_media_kueche]    # optional: further notify actions
    title: "{wann}: {tonnen}"
    message: "Bitte heute Abend rausstellen."
    actions:
      - {ack: true, label: "Steht draußen"}
  - id: lampe
    type: light_signal
    entity: light.stehleuchte
    pattern: {effect: blink, count: 3}    # blink | pulse, interval in seconds
    color_from: farbe            # colour from a keyword column, or color: "#ff8800"
    restore: true                # previous state (on/off, brightness, colour) afterwards
    quiet:
      - {from: "00:00", to: "10:00", mode: skip}
  - id: ansage
    type: announce
    players: [media_player.sonos_wohnzimmer]
    volume: 45
    tts: tts.piper               # default: the first TTS entity
    text: "Stell endlich die {tonne} raus!"
    text_plural: "Stell endlich {tonnen} raus!"
    quiet:
      - {from: "22:00", to: "08:00", mode: defer}   # send when the quiet time ends
    limit: {per_reminder: 1, min_interval: 60}      # at most once, 60 min apart
  - id: eigene
    type: action
    conditions:
      - {condition: state, entity_id: input_boolean.urlaub, state: "off"}
    conditions_match: all        # all | any
    actions:
      - action: script.turn_on
        target: {entity_id: script.muell_szene}
        data:
          variables: {text: "{{ wann }}: {{ tonnen }}"}
```

**On opportunity.** Instead of `when: now` a signal can wait for any Home
Assistant trigger (state, zone, tag, event …) – it fires whenever the trigger
fires while the reminder is open:

```yaml
  - id: lampe
    type: light_signal
    entity: light.stehleuchte
    color_from: farbe
    when:
      opportunity: {trigger: state, entity_id: light.stehleuchte, to: "on"}
      manual_only: true          # wall switch / app / dashboard, not automations
    limit: {per_reminder: 1}
  - id: ansage
    type: announce
    players: [media_player.sonos_wohnzimmer]
    text: "{person}, stell bitte die {tonne} raus!"
    when:
      opportunity: {trigger: state, entity_id: binary_sensor.haustuer, to: "on"}
```

`{person}` is who came home or operated the device, as far as Home Assistant
knows it. The triggers are only listened to while a reminder is open.

- **Push recipients:** in the card you simply tick persons; Läutwerk sends to
  their phones (companion app; persons without one are flagged). Optionally
  only to those who are at home, or to the responsible person. Notify actions
  are only needed for other devices.
- **Light:** German and English colour names, `#rrggbb` or `r,g,b`. Lamps
  without colour just blink. A lamp that was off is switched off again.
- **Announcement:** played with `announce: true`, so players that support it
  lower running music and continue afterwards. `volume` is the announcement
  volume for players that support it (e.g. Sonos).
- **Custom action:** any Home Assistant actions; the text variables are
  available as template variables (`{{ tonnen }}`, `{{ reminder_id }}`).
- **Try it:** `laeutwerk.test_signal` sends one signal immediately (`rule` +
  `signal`, or `config` with an unsaved signal).

### Repeat, snooze and ways to acknowledge

```yaml
repeat: {every: 1h, max: 5}      # while open: remind again every hour, 5 times
acknowledge:
  - {type: tag, tag_id: tonne}   # NFC tag (also before the reminder time)
  - {type: tag, tag_id: "{nfc}"} # tag per bin from the keyword column "nfc"
  - type: trigger                # door contact, zone, button: any trigger
    trigger: {trigger: zone, entity_id: person.steven, zone: zone.kult61, event: enter}
    early: false                 # true: also before the reminder time
signals:
  - type: notify
    audience: present
    message: "{wann}: {tonnen}"
    actions:
      - {ack: true, label: "Steht draußen"}
      - {snooze: 3h, label: "Später"}
```

**Tag per keyword:** with a column such as `nfc` (tag id per bin) and
`tag_id: "{nfc}"`, only the tag of the bin that is due acknowledges; for a
bundle (Rest + Bio on one day) each of its tags acknowledges the whole bundle.
Other tags do nothing. Fixed and variable tags can be mixed.

`laeutwerk.snooze` (or the push button) sets a reminder back to *planned*; it
reminds again when the time is over, unless it expires first.

### Extensions (0.6)

```yaml
# Sources besides calendars: to-do lists (open items with a due date),
# date / datetime entities, date helpers and timestamp or date sensors.
sources: [calendar.abfallkalender, todo.aufgaben, input_datetime.tuev]

# Due again n days after it was last acknowledged (no calendar needed).
# Overdue reminders (also overdue to-dos) remind daily until done.
interval: {every: 90}            # or "12w"; optional start: 2026-12-01

# Only active under conditions and / or in a season (event day, MM-DD).
activation:
  match: all                     # all | any
  conditions:
    - {condition: state, entity_id: input_boolean.urlaub, state: "off"}
  season: {from: "04-01", to: "11-30"}

# Responsible person: {zustaendig} in texts, push audience "assignee",
# statistics in get_rules (status.assignee_stats).
assignee:
  persons: [person.steven, person.anna]
  rotation: per_event            # fixed | weekly | per_event | after_last

# Escalation while open: stages start after a duration or at a time of day;
# a signal with "stage: n" is active from that stage on.
escalation:
  - {after: 2h}
  - {after: "21:30"}

# Home Assistant actions when a reminder is acknowledged
# (variables: person, via, titel, tonne … as in texts).
on_done:
  - action: counter.increment
    target: {entity_id: counter.tonnen_rausgestellt}
```

**Templates:** *+* in the card offers built-in templates (bins, birthdays,
maintenance, medication supply), your own templates (*Save as template* in
the editor) and *Import YAML*. `laeutwerk.export_rules` /
`laeutwerk.import_rules` (and *Export* in the editor) move rules as YAML.

### Entities (one device per rule)

| Entity | State |
|---|---|
| `sensor.laeutwerk_<rule>` | `planned` / `reminded` / `done` / `missed` / `inactive`, attributes with the event and its variables |
| `binary_sensor.laeutwerk_<rule>_offen` | on while a reminder waits to be acknowledged |
| `sensor.laeutwerk_<rule>_naechster_termin` | start of the next matching event |
| `button.laeutwerk_<rule>_erledigt` | acknowledge |
| `switch.laeutwerk_<rule>` | rule on/off |

### Actions and events

`laeutwerk.acknowledge`, `snooze` (`duration` or `until`), `reopen`, `trigger`,
`test_signal`, `get_rules`,
`export_rules`, `import_rules`, `create_rule`, `update_rule`,
`delete_rule`, `duplicate_rule`, `enable`, `disable`. Editing actions need an
admin (calls from automations are allowed).

Events on the bus: `laeutwerk_reminded`, `laeutwerk_signal_sent`,
`laeutwerk_acknowledged`, `laeutwerk_missed` (data: `rule_id`, `reminder_id`,
`titles`, `variables`, …).

## Card

The card registers itself – add it to a dashboard via *Add card → Läutwerk*
or in YAML:

```yaml
type: custom:laeutwerk-card
view: overview        # overview | rule
rule: muell           # with view: rule
rules: [muell, kult61]   # optional filter for the overview
show_upcoming: true
show_done: true
compact: false        # one line: the next task; tap to confirm done, snooze or add a rule
```

- **Today & upcoming:** open reminders with *Later* (3 h) and the done button
  of the rule, upcoming reminders, today's finished ones ("done by Steven ·
  20:41 · NFC tag"), "All done" when nothing is open. Updates live.
- **Rule editor** (administrators, *+* or tap a rule): calendar, keyword table
  with free columns (scrolls sideways), live preview of the next matches,
  reminder times, repeat, signals, ways to acknowledge, bundling and expiry.
- **Compact** (`compact: true`): always the next task in one line (open ones
  first, the one that expires first on top, then planned ones) with the rule's
  icon and the number of open tasks. Tapping opens a dialog: confirm *done*
  (also ahead of time for planned tasks), *Later*, pick another task, or
  create a new rule (administrators).
- **Everyday use:** *Later* offers 1 hour, 3 hours or tomorrow morning;
  after *Done* a short message offers **Undo** (also `laeutwerk.reopen`).
  Tap a reminder for its details: when it reminded, what was sent, what comes
  next, who is responsible, which tags count. Rules can be sorted and, with
  many rules, searched.
- **Editor:** steps are collapsed with a one-line summary (new rules are
  filled in step by step); missing things are checked before saving and
  shown at their step in plain words; unsaved changes need a confirmation and
  are kept as a draft in the browser. Keywords are suggested from the event
  titles of the calendar, NFC tags can be picked from the tags Home Assistant
  knows, signals can be tested before saving.
- **One rule** (`view: rule`): the rule's reminders plus its history (last
  10 finished reminders: done by whom and how, or missed).
- **Visual editor:** all options can be set in the dashboard's card editor.
- **Signal editor:** type, *immediately / on opportunity* with Home
  Assistant's trigger editor, *only if* with the condition editor, the fields
  of the type with variable chips and a text preview, limits and quiet times,
  *Test* and *Edit as YAML*.

The card bundle is 39 KB gzipped (measured with `gzip -9` on 0.7.0).

## Troubleshooting

- **Repairs:** a rule that refers to a calendar, light, speaker, person or
  notify action that does not exist (any more) gets a repair issue under
  *Settings → System → Repairs*. It disappears when everything is back.
- **Diagnostics:** *Settings → Devices & services → Läutwerk → ⋮ → Download
  diagnostics* (or on a rule's device page) contains the rules, their
  reminders and history – please attach it to bug reports.

## Development

Requires Python ≥ 3.14.2 and Node ≥ 20 (WSL2/Linux).

```bash
scripts/setup      # .venv + npm dependencies
scripts/develop    # local Home Assistant on http://localhost:8123 using ./config
scripts/lint       # ruff + eslint + prettier
scripts/test       # pytest + vitest
```

Card preview without Home Assistant (mocked data): `npm run build` in
`frontend/`, then `python3 -m http.server 8000` in the repo root and open
`http://localhost:8000/frontend/dev/preview.html` (`?page=editor`, `signal`,
`compact`, `rule`, `done`, `empty`; `?theme=light`, `?lang=en`, `?admin=0`).
`scripts/check_card.py` opens the card in the real frontend of the running dev
instance (headless Chromium) and takes screenshots.

The dev instance comes with two seeded local calendars ("Abfallkalender",
"Kult61") and helper stand-ins for presence, the front door and a lamp.

## License

MIT © Steven Glab

---

# Läutwerk (Deutsch)

Erinnerungen für Home Assistant: aus **Kalenderterminen** werden Signale, die
so lange aktiv bleiben, **bis jemand sie quittiert**.

> **Status:** frühe Entwicklung. 0.6 enthält alle geplanten Funktionen (Logik,
> Karte mit Regel-Editor, Vorlagen, Eskalation, Zuständigkeit …); 1.0 folgt nach
> dem Praxistest; Regeln legst du in der Karte an (*+*) oder
> mit der Aktion `laeutwerk.create_rule` (Beispiel oben). Fortschritt siehe [docs/TASKS.md](docs/TASKS.md).

Eine *Regel* beschreibt einen Anlass: welcher Kalender, welche Termine
(Stichwort-Tabelle), wann erinnern, welche Signale (Push, Licht, Ansage,
beliebige Home-Assistant-Aktion), wann nicht stören und woran man „erledigt“
erkennt (Push-Knopf, NFC-Tag, Türkontakt, Zone, Dashboard, Dienst). Jeder
passende Termin wird zu einer *Erinnerung* mit eigenem Zustand, die offen
bleibt, bis sie quittiert wird oder verfällt.

Läutwerk holt keine Termine selbst – Waste Collection Schedule,
Google-Kalender, CalDAV oder der lokale HA-Kalender bleiben die Quellen.

## Variablen und Mehrzahl

Jede Spalte der Stichwort-Tabelle wird eine Textvariable, z. B. `{tonne}`.
Bei mehreren Treffern entsteht automatisch die Mehrzahl mit angehängtem `n`:
`{tonnen}` = „Papiertonne und Biotonne“. Wo das keinen Sinn ergibt (z. B. bei
`artikel`), schaltest du die Mehrzahl im Spaltenkopf der Karte aus oder
schreibst die Spalte als `{name: artikel, plural: false}`. Dann gibt es kein
`{artikeln}`, und `{artikel}` enthält bei mehreren Treffern die verschiedenen
Werte, mit „und“ verbunden („die“ bzw. „die und den“). Ein eigener Name für
die Mehrzahl: `{name: tonne, plural: tonnen_liste}`.

## NFC-Tag je Tonne

Mit einer Spalte wie `nfc` (Tag-ID je Tonne) und `tag_id: "{nfc}"` quittiert
nur der Tag der Tonne, die gerade fällig ist – im Editor unter „Erledigt
durch“ per Variablen-Chip. Bei einem Bündel (Rest + Bio am selben Tag)
quittiert jeder der beiden Tags die ganze Erinnerung, andere Tags nichts.
Feste und variable Tags lassen sich mischen.

## Bedienung (seit 0.7)

- **Kompakte Karte** (`compact: true`): immer die nächste Aufgabe in einer
  Zeile mit Symbol und Zahl der offenen. Antippen öffnet ein Fenster: mit
  Nachfrage als erledigt markieren (geplante auch schon vorab), „Später“,
  eine andere Aufgabe wählen oder eine neue Regel anlegen (Admins).
- Der Erledigt-Knopf in der Karte ist nur noch ein ✓; die Beschriftung kommt
  aus dem Erledigt-Knopf des Push-Signals.
- **Später** bietet 1 Stunde, 3 Stunden oder „Morgen früh“ (07:00); nach
  **Erledigt** erscheint kurz **Rückgängig** (auch als Aktion `laeutwerk.reopen`).
- Eine Erinnerung **antippen** zeigt Details: wann erinnert, was gesendet
  wurde, was als Nächstes kommt, wer zuständig ist, welche Tags zählen.
- Im **Regel-Editor** sind die Schritte eingeklappt mit Zusammenfassung; neue
  Regeln füllst du Schritt für Schritt („Weiter“). Fehlendes wird vor dem
  Speichern am jeweiligen Schritt angezeigt, ungespeicherte Änderungen
  brauchen eine Bestätigung und bleiben als Entwurf im Browser.
- **Stichwörter** werden aus den Termintiteln des Kalenders vorgeschlagen,
  **NFC-Tags** aus den in Home Assistant angelernten Tags ausgewählt, und
  Signale lassen sich schon vor dem Speichern **testen**.
- **Regeln sortieren** (↑/↓) und bei vielen Regeln **durchsuchen**.

## Installation (HACS, benutzerdefiniertes Repository)

Benötigt Home Assistant 2026.11 oder neuer.

1. HACS → ⋮ → *Benutzerdefinierte Repositories* → `https://github.com/StiviDrum/laeutwerk`, Typ **Integration**.
2. **Läutwerk** installieren, Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → Läutwerk*.
