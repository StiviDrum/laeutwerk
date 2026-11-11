# Läutwerk

Reminders for Home Assistant that turn **calendar events** into signals which
stay active **until someone acknowledges them**.

> **Status:** early development – not usable yet. See
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

Available with the first release.

1. HACS → ⋮ → *Custom repositories* → `https://github.com/StiviDrum/laeutwerk`, type **Integration**.
2. Install **Läutwerk**, restart Home Assistant.
3. *Settings → Devices & services → Add integration → Läutwerk*.

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

> **Status:** frühe Entwicklung – noch nicht benutzbar. Fortschritt siehe
> [docs/TASKS.md](docs/TASKS.md).

Eine *Regel* beschreibt einen Anlass: welcher Kalender, welche Termine
(Stichwort-Tabelle), wann erinnern, welche Signale (Push, Licht, Ansage,
beliebige Home-Assistant-Aktion), wann nicht stören und woran man „erledigt“
erkennt (Push-Knopf, NFC-Tag, Türkontakt, Zone, Dashboard, Dienst). Jeder
passende Termin wird zu einer *Erinnerung* mit eigenem Zustand, die offen
bleibt, bis sie quittiert wird oder verfällt.

Läutwerk holt keine Termine selbst – Waste Collection Schedule,
Google-Kalender, CalDAV oder der lokale HA-Kalender bleiben die Quellen.

## Installation (HACS, benutzerdefiniertes Repository)

Verfügbar ab dem ersten Release.

1. HACS → ⋮ → *Benutzerdefinierte Repositories* → `https://github.com/StiviDrum/laeutwerk`, Typ **Integration**.
2. **Läutwerk** installieren, Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → Läutwerk*.
