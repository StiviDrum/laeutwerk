# SPEC.md – Läutwerk

Source of truth for features, data model, entities and API (German, taken from `CLAUDE.md` part B). Keep in sync when decisions change.

## B1. Idee

Eine **Regel** beschreibt einen Anlass. Jeder passende Termin erzeugt daraus eine **Erinnerung** mit eigenem Zustand. Die Erinnerung bleibt offen, bis sie quittiert wird oder verfällt. Statt pro Anlass eine Automation zu bauen, legt man eine Regel an: welche Quelle, welche Termine, wann erinnern, welche Signale, wann nicht stören, woran man „erledigt“ erkennt.

Abgrenzung: Läutwerk holt keine Termine selbst. Waste Collection Schedule, Google-Kalender, CalDAV oder der lokale HA-Kalender bleiben die Quellen. Läutwerk ist die Schicht zwischen „Termin steht im Kalender“ und „jemand hat es erledigt“.

## B2. Datenmodell einer Regel

| Baustein | Bedeutung |
|---|---|
| Quelle | ein oder mehrere Kalender (ab 0.6 auch Datums-Sensoren, Datums-Helfer, To-do-Listen mit Fälligkeit, Intervall ab Erledigung) |
| Filter / Stichwort-Tabelle | Stichwörter (enthält / beginnt mit / Regex), optional nur Ganztags-Termine; **frei definierbare Spalten**, jede Spalte wird eine Variable (siehe B4) |
| Zeitpunkte | relativ zum Terminbeginn, mehrere pro Regel (z. B. `-1d 17:00`, `-2h`) |
| Signale | beliebig viele, jedes voll konfigurierbar (siehe B3) |
| Quittierung | Knopf in der Push, NFC-Tag (`tag_scanned`), Taster, Türkontakt, Zone, Dashboard, Dienst. Die Tag-ID darf Variablen enthalten (`tag_id: "{nfc}"`): je Termin aufgelöst, es quittiert nur der Tag des fälligen Treffers (seit 0.6.3) |
| Wiederholen | einmal, alle n Minuten, bis erledigt (mit Maximum) |
| Bündeln | Termine derselben Regel am selben Tag werden **eine** Erinnerung („Morgen: Papier + Bio“); ein Quittieren erledigt alle |
| Verfallen | wann eine offene Erinnerung als verpasst gilt (z. B. Abholtag 12:00) |
| Aktivierung (0.6) | Regel nur unter Bedingungen aktiv, alle/eine, plus Saison-Zeitraum |

Beispiel (Speicherform, über Karte und Dienste editierbar):

```yaml
id: muell
name: Müll rausstellen
sources: [calendar.abfallkalender]
filter:
  all_day: true
  keywords:
    columns: [tonne, farbe, artikel]
    rows:
      - {match: Papier, tonne: Papiertonne, farbe: blau, artikel: die}
      - {match: Bio, tonne: Biotonne, farbe: grün, artikel: die}
      - {match: Rest, tonne: Restmülltonne, farbe: grau, artikel: die}
      - {match: Gelb, tonne: gelben Sack, farbe: gelb, artikel: den}
reminders:
  - {at: "-1d 17:00"}
signals:
  - id: push
    type: notify
    when: now
    audience: present
    title: "{wann}: {tonnen}"
    message: "Bitte heute Abend rausstellen."
    actions: [{ack: true, label: "Steht draußen"}, {snooze: "3h", label: "Später"}]
  - id: lampe
    type: light_signal
    entity: light.leuchte_stehleuchte
    pattern: {effect: blink, count: 3}
    color_from: farbe
    when: {opportunity: {trigger: state, entity_id: light.leuchte_stehleuchte, to: "on"}, manual_only: true}
    limit: {per_reminder: 1}
    quiet: [{from: "00:00", to: "10:00", mode: skip}]
    restore: true
  - id: ansage
    type: announce
    players: [media_player.sonos_wohnzimmer]
    volume: 45
    text: "Stell endlich die scheiß {tonne} raus!"
    text_plural: "Stell endlich die scheiß {tonnen} raus!"
    when: {opportunity: {trigger: state, entity_id: binary_sensor.haustuer, to: "on"}}
    limit: {per_reminder: 1}
    quiet: [{from: "22:00", to: "08:00", mode: skip}]
acknowledge:
  - {type: notify_action}
  - {type: tag, tag_id: tonne}
repeat: none
bundle: true
expire: "event_day 12:00"
```

(`binary_sensor.haustuer` ist ein Platzhalter.)

## B3. Signale – voll anpassbar

Ein Signal ist ein Baustein aus fünf Teilen. Push, Licht und Ansage sind nur vorbereitete Schnelleditoren; „Eigene Aktion“ erlaubt beliebige HA-Aktionen.

| Teil | Möglichkeiten |
|---|---|
| Art | Push (Mobile App `notify`, mit Aktionsknöpfen), Licht (Muster blinken/pulsieren, Anzahl, Farbe fest oder aus Spalte), Ansage (`tts.speak` mit `announce: true`, Lautsprecher, Lautstärke, Stimme/Engine), Eigene Aktion (HA-Aktions-Editor, Skript, Szene …) |
| Wann | **sofort** zum Erinnerungszeitpunkt oder **bei Gelegenheit**: jeder HA-Trigger (Zustand, Zone, Bewegung, NFC-Tag, Ereignis), aktiv nur zwischen Erinnerungszeitpunkt und Quittierung/Verfall |
| Nur wenn | Bedingungen mit alle/eine (wie Zeitwerk) |
| Was passiert | Felder je Art, überall Variablen; jederzeit als YAML bearbeitbar |
| Grenzen | Häufigkeit (max. pro Erinnerung, Mindestabstand), Ruhezeit je Signal (auslassen oder nachholen, sobald sie endet), danach Zustand wiederherstellen |

Wichtige Details:

- **Nur echte Bedienung:** „Lampe eingeschaltet“ zählt nur, wenn der `context` nicht von einer Automation/einem Skript stammt (z. B. der Lichtwecker löst nichts aus). Option `manual_only`.
- **Zustand wiederherstellen:** vor dem Licht-Signal Zustand sichern (Helligkeit, Farbe, an/aus), danach exakt wiederherstellen; wer die Lampe einschaltet, hat danach normales Licht.
- **Ansage:** laufende Musik wird durch `announce` abgesenkt und danach fortgesetzt; eigene Lautstärke.
- **Zielgruppe** für Push: alle, nur Anwesende, bestimmte Personen, Zuständige (0.6).
- Jedes Signal ist im Editor einzeln testbar (Dienst `laeutwerk.test_signal`).

## B4. Variablen

| Quelle | Variablen |
|---|---|
| Termin (immer) | `{titel}`, `{rest}` (Titel ohne gefundenes Stichwort), `{beschreibung}`, `{ort}`, `{kalender}`, `{wann}` (heute/morgen/am Donnerstag), `{datum}`, `{uhrzeit}` |
| Gelegenheit | `{person}` (wer heimkam, wer die Lampe schaltete – soweit aus `context`/Trigger ermittelbar) |
| Stichwort-Tabelle | je Spalte eine Variable mit frei gewähltem Namen, z. B. `{tonne}`, `{farbe}`, `{artikel}`, `{aufgabe}`, `{nfc}` (auch in der Tag-ID zum Quittieren nutzbar) |
| Mehrere Treffer | je Spalte automatisch die Mehrzahl mit angehängtem `n`, verbunden mit „und“: `{tonnen}` = „Papiertonne und Biotonne“. Je Spalte abschaltbar (`{name: artikel, plural: false}`, Umschalter im Spaltenkopf) – dann keine Mehrzahl-Variable, und die Spalten-Variable enthält bei mehreren Treffern die verschiedenen Werte mit „und“ verbunden; eigener Mehrzahl-Name mit `{name: tonne, plural: tonnen_liste}` (seit 0.6.2) |
| Zuständigkeit (0.6) | `{zustaendig}` |

Textfelder mit einer Einzahl- und einer Mehrzahl-Variante (`text` / `text_plural`) für saubere Grammatik. Der Editor zeigt unter jedem Textfeld die verfügbaren Variablen als Chips und eine Vorschau mit dem nächsten echten Termin.

## B5. Lebenszyklus einer Erinnerung

Zustände: **geplant** (Termin gefunden) → **erinnert** (Zeitpunkt erreicht, Sofort-Signale gesendet, Gelegenheits-Signale scharf) → **erledigt** (quittiert, mit Person und Zeit). Weitere Übergänge:

- geplant → erledigt: schon vorher quittiert (z. B. NFC an der Tonne vor 17 Uhr).
- erinnert → geplant: „später erinnern“ (Snooze).
- erinnert → **verpasst**: Verfallszeit erreicht ohne Quittung (Ereignis `laeutwerk_missed`).

Im Zustand „erinnert“ wiederholt sich die Erinnerung, falls konfiguriert. Ruhezeiten wirken nur auf einzelne Signale.

## B6. Entitäten, Dienste, Ereignisse

Jede Regel = ein Gerät.

| Entität | Zustand | Attribute |
|---|---|---|
| `sensor.laeutwerk_<regel>` | geplant / erinnert / erledigt / verpasst / inaktiv | `next_event`, `event_title`, `event_start`, `bundled_titles`, `variables`, `acknowledged_by`, `acknowledged_at` |
| `binary_sensor.laeutwerk_<regel>_offen` | an, solange eine Erinnerung offen ist | `since` |
| `sensor.laeutwerk_<regel>_naechster_termin` | Zeitstempel des nächsten Treffers | `title`, `days_until` |
| `button.laeutwerk_<regel>_erledigt` | quittieren | – |
| `switch.laeutwerk_<regel>` | Regel an/aus | – |

Dienste: `laeutwerk.acknowledge` (Regel oder alle offenen, optional Person), `snooze`, `trigger` (sofort auslösen), `test_signal`, `get_rules` (Response-Daten), `create_rule`, `update_rule`, `delete_rule`, `duplicate_rule`, `enable`/`disable` (eine, Liste, alle). Bearbeitungsdienste nur Admin; Aufrufe aus Automationen erlaubt. Dienstbeschreibungen so schreiben, dass ein Assistent über MCP die Integration allein bedienen kann (wie Zeitwerk).

Ereignisse: `laeutwerk_reminded`, `laeutwerk_signal_sent`, `laeutwerk_acknowledged`, `laeutwerk_missed`.

WebSocket (Admin für Schreibzugriffe): `laeutwerk/rules/list|get|create|update|delete|subscribe`, `laeutwerk/preview` (nächste Treffer einer Regel inkl. Variablen, auch für eine ungespeicherte Regel), `laeutwerk/history` (Verlauf je Regel).

## B7. Erweiterungen (Meilenstein 0.6)

| Erweiterung | Inhalt |
|---|---|
| Intervall ab Erledigung | Fälligkeit relativ zur letzten Quittierung (z. B. Filter 90 Tage nach dem letzten Tausch) |
| Eskalationsstufen | Stufen mit Abstand, solange offen, jede mit eigenen Signalen/Empfängern (17:00 Push → beim Heimkommen Lampe → 21:30 Ansage an alle) |
| Zuständigkeit und Wechsel | feste Person oder Wechsel (wöchentlich, pro Termin, „wer zuletzt erledigt hat“), `{zustaendig}`, Signale optional nur an diese Person, Statistik |
| Aktivierung | ganze Regel nur unter Bedingungen aktiv, alle/eine, Saison-Zeitraum |
| Aktionen beim Erledigen | Quittieren löst eigene HA-Aktionen aus (Einkaufsliste, Zähler, Kalendertermin markieren) |
| Weitere Quellen | Datums-Sensoren, Datums-Helfer, To-do-Listen mit Fälligkeit |
| Vorlagen | Regeln als Vorlage speichern, YAML-Export/-Import, mitgelieferte Vorlagen (Müll, Geburtstag, Wartung, Medikamente-Vorrat) im Assistenten für neue Regeln |

Kein Sprachassistent.

## B8. Referenzfälle für Tests und Doku

| Regel | Quelle/Filter | Erinnern | Signale | Erledigt durch |
|---|---|---|---|---|
| Müll rausstellen | Abfallkalender, Stichwörter Papier/Bio/Rest/Gelb mit Spalten tonne/farbe/artikel | Vortag 17:00 | Push an Anwesende (sofort); Stehleuchte blinkt beim Einschalten, max. 1×, nicht 0–10 Uhr, Farbe aus `{farbe}`; Ansage beim Öffnen der Haustür, nicht 22–8 Uhr | Push-Knopf oder NFC-Tag „tonne“ |
| Kult61-Dienst | Kult61-Kalender, beginnt mit „Dienst:“ | Vortag 20:00 und 2 h vorher | Push an Steven: „Denk an deinen Dienst {wann}: {rest}, ab {uhrzeit}.“ | Push-Knopf oder Zone Kult61 betreten |
| Geburtstage | Geburtstagskalender, ohne Stichwort | 7 Tage vorher, am Tag 09:00 | Push + Badge: „{titel} hat {wann} Geburtstag“ | Knopf „Gratuliert“ |
| Wartung | lokaler Kalender bzw. ab 0.6 Intervall, Spalte `{aufgabe}` | am Tag 18:00, täglich bis erledigt | Push + Badge: „{wann}: {aufgabe} ({titel})“ | Knopf oder NFC-Tag am Gerät |

