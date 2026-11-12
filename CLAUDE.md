# CLAUDE.md – Läutwerk (Home-Assistant-Integration + Karte)

Du bist Lead-Entwickler von **Läutwerk**, einer HACS-Integration für Home Assistant mit eigener Lovelace-Karte. Läutwerk macht aus Kalenderterminen (und später Intervallen) Erinnerungen mit frei konfigurierbaren Signalen, die so lange aktiv bleiben, bis jemand sie quittiert.

Projektinhaber ist **Steven** (Deutschland, erfahrener Home-Assistant-Nutzer, SPS-/Automatisierungstechniker, kein Vollzeit-Webentwickler). Läutwerk ist das Geschwisterprojekt von **Zeitwerk** (`https://github.com/StiviDrum/zeitwerk`): gleiche Struktur, gleiche Qualität, gleicher Look.

Diese Datei ist die einzige Vorgabe. Sie enthält Arbeitsweise (Teil A), Spezifikation (Teil B), Design (Teil C) und Meilensteine (Teil D). Lege beim Scaffolding `docs/SPEC.md`, `docs/DESIGN.md` und `docs/TASKS.md` aus den Teilen B–D an und halte sie aktuell; diese Datei bleibt als `CLAUDE.md` im Repo.

---

# Teil A – Arbeitsweise

## A0. Erster Schritt: Repo erfragen

**Bevor du irgendeine Datei schreibst, frag Steven auf Deutsch nach dem GitHub-Repo-Link**, z. B.:

> „Hi Steven! Wie lautet der Link zu deinem GitHub-Repo für Läutwerk?“

Danach:

1. Werkzeuge prüfen: `git --version`, `node --version` (≥ 20), `python3 --version` (die Version, die das aktuelle Home Assistant verlangt – nachschlagen), `gh auth status`. Fehlt etwas: in einer kurzen deutschen Nachricht sagen, was und wie man es unter WSL2/Ubuntu installiert; mit allem weitermachen, was es nicht braucht.
2. Liegt diese `CLAUDE.md` in einem leeren Ordner, wird dieser Ordner das Repo: `git init`, Remote setzen, `git pull` falls das Repo nicht leer ist. Ist das Remote-Repo nicht leer: kurz zusammenfassen (3 Zeilen) und einmal fragen, wie weiter.
3. Zeitwerk als Referenz klonen, **neben** das Projekt, nicht hinein: `git clone https://github.com/StiviDrum/zeitwerk ../zeitwerk-ref` (falls `~/zeitwerk` schon existiert, das nehmen). Übernimm daraus Struktur, Skripte, CI, Store-/Migrationsmuster, Bedingungslogik (alle/eine), WebSocket-API-Muster, Dienste mit Response-Daten, Karten-Grundgerüst, Theme-Variablen und Übersetzungsaufbau. Kopiere bewusst und angepasst, nicht blind.
4. Scaffold (Teil D, M0), erster Commit `chore: scaffold project`, pushen, prüfen.
5. Dann **loslegen**: die Meilensteine aus `docs/TASKS.md` der Reihe nach abarbeiten, ohne für jeden Schritt um Erlaubnis zu fragen. Nur fragen, wenn eine Entscheidung wirklich Stevens ist (sichtbare Namen, Lizenz, Veröffentlichung, Unumkehrbares) oder du blockiert bist.

## A1. Kommunikation

- Mit Steven **auf Deutsch**, kurz und konkret.
- Nach jedem Meilenstein: kurze deutsche Zusammenfassung (was geht, wie testen, was kommt), `docs/TASKS.md` aktualisieren.
- Code, Kommentare, Bezeichner, Commit-Messages, README (Englisch zuerst, deutscher Abschnitt darunter), CHANGELOG: **Englisch**.

## A2. Git

- Arbeit auf `main`, kleine Commits nach Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `ci:`).
- Größere oder riskante Vorhaben auf einem Feature-Branch. Der Orchestrator entscheidet selbst, wann eine Änderung stabil ist (`scripts/check` grün, Build ok, bei UI-Änderungen im echten Frontend gesichtet), führt sie dann ohne Rückfrage per Fast-Forward/Merge nach `main` zusammen und pusht (Stevens Freigabe vom 11.11.2026).
- Nach jeder erledigten Aufgabe pushen. CI muss grün bleiben; rote CI zuerst reparieren.
- Am Ende jedes Meilensteins: Version in `manifest.json` + `package.json`, `CHANGELOG.md`, Tag `v0.x.0`, Tag pushen (Release-Workflow baut das ZIP). **Releases nicht als Pre-Release markieren**, sonst bietet HACS Commit-Stände statt Versionen an (bei Zeitwerk passiert).
- Kein Force-Push auf `main`. Keine Secrets, Tokens, `.storage`-Dateien oder persönlichen Daten committen.

## A3. Technik (entschieden)

| Bereich | Wahl |
|---|---|
| Domain | `laeutwerk`, Anzeigename „Läutwerk“. Alle Dienste, Entitäten, WebSocket-Typen und das Karten-Element tragen dieses Präfix (`custom:laeutwerk-card`) |
| Backend | Python, nur async, typisiert, Dataclasses in `model.py` |
| Speicher | `homeassistant.helpers.storage.Store`, Key `laeutwerk`, versioniert mit Migrationen |
| Aktionen / Bedingungen / Auslöser | HA-eigene Helfer: `script.Script`, `condition`, `trigger` (für „bei Gelegenheit“ dieselben Trigger-Schemas wie Automationen), validiert mit `cv.SCRIPT_SCHEMA`, `cv.CONDITIONS_SCHEMA`, `cv.TRIGGER_SCHEMA` |
| Kalender lesen | Aktion `calendar.get_events` (Response-Daten), keine Interna |
| Frontend | TypeScript + Lit 3, Rollup → eine ES-Modul-Datei `custom_components/laeutwerk/frontend/laeutwerk-card.js` |
| Karten-Registrierung | wie Zeitwerk: statischer Pfad + `frontend.add_extra_js_url`, keine manuelle Ressource |
| Lint / Tests / CI | ruff, eslint + prettier, pytest-homeassistant(-custom-component), vitest; GitHub Actions mit hassfest, HACS-Validierung, Lint, Tests, Build |
| Lizenz | MIT, „Steven Glab“ |

**Home-Assistant-APIs ändern sich oft.** Für jede verwendete API (Config-Flow, Entity-Basisklassen, WebSocket-API, Frontend-Registrierung, `async_track_*`, Tags, Mobile-App-Aktionen, TTS) die aktuelle Entwicklerdoku oder den HA-Core-Quellcode prüfen, nicht aus dem Gedächtnis arbeiten.

## A4. Lokale Entwicklung (WSL2)

- Entwicklung in WSL2/Ubuntu im Linux-Dateisystem (`~/laeutwerk`), nicht unter `/mnt/c/...`.
- Skripte wie bei Zeitwerk: `scripts/setup`, `scripts/develop` (lokale HA-Testinstanz unter `http://localhost:8123` mit `./config`), `scripts/lint`, `scripts/check` (nur lesend), `scripts/test`, `npm run watch` für die Karte.
- `config/configuration.yaml` der Testinstanz bildet Stevens Fälle mit Helfern nach: ein lokaler Kalender „Abfallkalender“ mit Terminen Papier/Bio/Rest/Gelb, ein Kalender „Kult61“ mit „Dienst: …“-Terminen, `input_boolean` als Stand-ins für Anwesenheit, Haustür und Lampe, `light` per Template/Demo-Plattform zum Blinken.
- **Niemals mit Stevens produktivem Home Assistant verbinden oder ihn verändern.** Steven installiert Läutwerk selbst über HACS, sobald ein Release existiert.
- Zeitabhängige Tests mit eingefrorener Zeit (`freezer`, `async_fire_time_changed`); Sommer-/Winterzeit-Tage (letzter Sonntag im März/Oktober, Europe/Berlin) sind Pflicht.

## A5. Modelle

Steven arbeitet ggf. abwechselnd mit **Claude Fable 5.1** (Architektur, Engine, schwierige Logik) und **Claude Opus 5.5** (Karte, Feinschliff, Übersetzungen, Fixes). Deshalb: Der gesamte Projektstand muss jederzeit aus dem Repo verständlich sein. `docs/TASKS.md` nach jeder Aufgabe abhaken, offene Entscheidungen und Erkenntnisse dort notieren. Ein neues Modell oder eine neue Sitzung liest `CLAUDE.md` + `docs/TASKS.md` und macht beim nächsten offenen Punkt weiter.

## A6. Qualität

- Jede Regel aus Teil B hat Tests: Filter und Stichwort-Tabelle, Bündeln, Zeitpunkte relativ zum Termin, Wiederholen, Verfallen, Ruhezeiten (auslassen/nachholen), Gelegenheiten (Fenster, Häufigkeit, nur echte Bedienung), Zustand wiederherstellen, Quittierung über alle Wege, Neustart ohne doppelte Signale, Sommer-/Winterzeit.
- Signale werden genau einmal pro Anlass ausgelöst; gesendete Zeitpunkte und offene Erinnerungen überleben Neustarts.
- Listener nur auf die Entitäten, die eine Regel wirklich braucht; beim Entladen alles sauber abmelden (testen).
- WebSocket- und Bearbeitungsdienste: nur Admin (Aufrufe aus Automationen erlaubt), volle Validierung, verständliche Fehlermeldungen.
- Karte: keine Fehler, wenn `hass` fehlt, eine Regel fehlt oder die WebSocket-Verbindung weg ist – freundlicher Fehlerzustand.
- Übersetzungen `de` + `en` für Integration und Karte.
- Reparaturen (`issue_registry`) bei Regeln mit fehlenden Entitäten oder Kalendern.
- Diagnose-Download wie bei Zeitwerk.

## A7. Nicht tun

- Keine Abhängigkeit von Bubble Card, card-mod oder anderen Custom Cards – nur kompatibel aussehen.
- Keine großen UI-Bibliotheken; HA-eigene Elemente (`ha-selector`, `ha-icon`, `ha-switch`, `ha-dialog`, Aktions-/Bedingungs-/Trigger-Editor) nutzen, mit Fallback.
- Keine Zahlen in Doku/README erfinden (Bundle-Größe usw.) – messen.
- Keinen Sprachassistenten-/Assist-Teil bauen (bewusst ausgeschlossen).

## A8. Orchestrierung mit Subagenten

Die Hauptsitzung (Opus / Fable) ist **Orchestration-Lead**: Sie plant, zerlegt Aufgaben, delegiert schreibenden Code an Subagenten, lässt prüfen und **committet selbst – erst nach grünen Checks**. Subagenten liegen in `.claude/agents/`:

| Agent | Modell | Domäne | Darf |
|---|---|---|---|
| `ha-backend` | sonnet | `custom_components/laeutwerk/**` (ohne gebautes `frontend/`), `tests/**`, `scripts/*.py` | Code + Tests schreiben, `git add` |
| `lovelace-frontend` | sonnet | `frontend/src/**`, `frontend/tests/**` | Code + Tests schreiben, `git add` |
| `tester` | haiku | ganzes Repo, nur lesend | Checks ausführen, berichten |
| `docs-writer` | haiku | `README.md`, `CHANGELOG.md`, `docs/*.md` | Doku-Text nach genauem Auftrag, `git add` |

Ablauf je Aufgabe:
1. Plan kurz in `docs/TASKS.md` festhalten (offene Aufgabe), bei Bedarf in Backend- und Frontend-Teil zerlegen; Schnittstelle (Datenformat, WebSocket-Typ, Feldnamen) im Auftrag an beide Agenten **ausdrücklich** nennen.
2. Auftrag an den Agenten: Ziel, betroffene Dateien/Funktionen, erwartete Tests, Akzeptanzkriterien. Unabhängige Aufträge parallel starten.
3. `tester` ausführen lassen (`scripts/check` + `npm run build`). Rot → gezielter Fix-Auftrag an den zuständigen Agenten.
4. Orchestrator prüft den Diff (`git diff --staged`), sichtet UI-Änderungen bei Bedarf im echten Frontend (`scripts/check_card.py`, lokale Testinstanz), pflegt Doku (`README.md`, `CHANGELOG.md`, `docs/*`, Versionen) und committet nach Conventional Commits; Push/Tag/Release wie in A2.

Sparsam arbeiten (Stevens Vorgabe vom 12.11.2026): Agenten mit `effort` low (haiku) bzw. medium (sonnet), kurze präzise Aufträge, gezielte Tests beim Iterieren und die volle Suite nur einmal am Ende, kurze Berichte. Einfache Aufgaben (Checks, Doku-Text) gehen an die Haiku-Agenten.

Regeln für alle Subagenten: nur in der eigenen Domäne arbeiten; **niemals `git commit`, `git push`, `git tag` oder Branch-/History-Befehle**; nie Stevens produktives Home Assistant ansprechen; `config/.storage` und Secrets nie lesen. Kleine, klar umrissene Aufgaben (Architektur und knifflige Engine-Logik behält der Orchestrator).

Befehle (aus dem Repo-Root):

| Zweck | Befehl |
|---|---|
| Setup | `scripts/setup` (`.venv` mit Python ≥ 3.14, `npm ci`) |
| Formatieren + Autofix | `scripts/lint` (ändert Dateien) |
| Alle Checks, nur lesend | `scripts/check` (ruff format --check, ruff check, prettier --check, eslint, tsc, pytest, vitest) |
| Tests | `scripts/test` (pytest + vitest) |
| Karte bauen | `cd frontend && npm run build` (bzw. `npm run watch`) |
| Übersetzungen erzeugen | `python scripts/build_translations.py` |
| Lokale HA-Testinstanz | `scripts/develop` → `http://localhost:8123` |
| Echtes Frontend prüfen | `python scripts/check_card.py <ausgabeordner>` (Testinstanz muss laufen) |

Token-Schutz: `.claude/settings.json` sperrt das Lesen von `.venv`, `node_modules`, Caches, gebautem Bundle, `config/.storage` und Logs (`.claudeignore` dokumentiert dieselbe Liste; beide synchron halten).

---

# Teil B – Spezifikation

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
| Quittierung | Knopf in der Push, NFC-Tag (`tag_scanned`), Taster, Türkontakt, Zone, Dashboard, Dienst |
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
| Stichwort-Tabelle | je Spalte eine Variable mit frei gewähltem Namen, z. B. `{tonne}`, `{farbe}`, `{artikel}`, `{aufgabe}` |
| Mehrere Treffer | je Spalte automatisch die Mehrzahl mit angehängtem `n`, verbunden mit „und“: `{tonnen}` = „Papiertonne und Biotonne“ |
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

---

# Teil C – Design der Karte

Freigegebenes Mockup (vier Handy-Bildschirme, 390 px breit) auf Stevens Claude-Design-Seite „Merkwerk Karte“ (der Name „Merkwerk“ dort ist veraltet). Die Karte muss in Stevens dunklem monochromen Theme „Claude Glass“ mit Bubble Card **und** in den HA-Standard-Themes hell/dunkel gut aussehen. **Look, Token-System und Komponenten-Maße 1:1 wie die Zeitwerk-Karte** (siehe `docs/DESIGN.md` im Zeitwerk-Repo): Theme-Variablen mit Fallbacks, Radius 26 für Karten, Pillen-Höhen 44–52 px, Touch-Ziele ≥ 44 px, keine Web-Fonts, kein `backdrop-filter`.

## C1. Ansichten

1. **Heute & demnächst** (`view: overview`, Standard)
   - Kopf: Datum, „Erinnerungen“, Chip „N offen“.
   - **Offen:** je Erinnerung eine Karte: Symbol in Regelfarbe (44 px Kreis), Titel („Morgen: Papier + Bio“), Unterzeile (Regel · Termin), Status-Chip (z. B. „erinnert 17:00“, „fällig seit gestern“), Farbpunkte der Treffer aus der Spalte `farbe`, Knöpfe „Später“ (Umriss, 1/3) und Erledigt-Knopf mit Regel-Text (z. B. „Steht draußen“, gefüllt, 2/3). Aktive Erinnerungen mit Akzent-Rahmen.
   - **Demnächst:** ruhige Liste (Symbol, Titel, „Erinnerung So 17:00“, Datum rechts).
   - **Erledigt:** durchgestrichen, „erledigt von Steven · Mo 20:41 · NFC-Tag“, bis Tagesende sichtbar.
   - Leerzustand „Alles erledigt“.
2. **Regel-Editor** (Admin), Schritte untereinander in Karten:
   1. Kalender (Quelle wählen)
   2. Welche Termine: **Stichwort-Tabelle** mit Spalten (Stichwort + frei benannte Variablen), Knöpfe „+ Stichwort“ und „+ Spalte (Variable)“, **horizontal scrollbar bei vielen Spalten** (`overflow-x: auto`, feste Spaltenbreiten), Hinweis zur automatischen Mehrzahl, Vorschau der nächsten Treffer (gebündelt markiert).
   3. Wann erinnern: Zeitpunkt-Chips + „+ Zeitpunkt“, Wiederholen (einmal / stündlich / bis erledigt).
   4. Signale: Liste mit Schalter je Signal und Kurzbeschreibung („blinkt beim Einschalten · max. 1× · nicht 0–10 Uhr“); ausgeklappt: Umschalter „sofort / bei Gelegenheit“, Chips für Auslöser und Grenzen, bei Ansage Textfelder (Einzahl/Mehrzahl), Variablen-Chips, Lautsprecher-Chip, Vorschau des gesprochenen Satzes mit Test-Knopf; darunter „+ Signal hinzufügen“.
   5. Erledigt durch: Push-Knopf, NFC-Tag (mit „zuletzt …“), „+ Türkontakt, Zone oder Taster“.
   6. Feinheiten: Bündeln, Verfällt.
   - Unten Abbrechen / Speichern.
3. **Signal bearbeiten** (Unterseite/Dialog): Art (4 Kacheln Push/Licht/Ansage/Eigene), Wann (sofort / bei Gelegenheit + gewählter Trigger mit HA-Trigger-Editor), Nur wenn (alle/eine + Bedingungen), Was passiert (Felder je Art, Variablen), Grenzen (Häufigkeit, Ruhezeit, danach wiederherstellen), Testen / Übernehmen, „Als YAML bearbeiten“.
4. **Kompakt** (`compact: true`): einzeilig für den Dashboard-Kopf (Symbol mit Badge, „Morgen: Papier + Bio“, Zusatzzeile weiterer offener Erinnerungen, Knopf „Erledigt“).

Push-Benachrichtigung (Mobile App): Titel und Text aus der Regel, Aktionsknöpfe „Steht draußen“ / „Später“.

## C2. Kartenkonfiguration

```yaml
type: custom:laeutwerk-card
view: overview        # overview | rule
rule: muell           # bei view: rule
rules: [muell, kult61]   # optional Filter für overview
show_upcoming: true
show_done: true
compact: false
```

Visueller Karteneditor (`getConfigElement`), `getStubConfig`, `getGridOptions`.

## C3. Performance

- Rendern nur bei relevanten Änderungen (`shouldUpdate` auf die eigenen Entitäten).
- Regeln per `laeutwerk/rules/subscribe` (eine Subscription pro Karte, Abmelden in `disconnectedCallback`).
- Editor-Teile nur rendern, wenn geöffnet; Bundle klein halten und messen.

---

# Teil D – Meilensteine (Startinhalt für `docs/TASKS.md`)

Abhaken mit `- [x]`, Erkenntnisse kurz unter die Aufgabe schreiben.

## M0 – Scaffold
- [ ] Repo-Link erfragt, Werkzeuge geprüft, Zeitwerk als Referenz geklont
- [ ] Struktur wie Zeitwerk (`custom_components/laeutwerk`, `frontend/`, `tests/`, `scripts/`, `config/`, `docs/`), `docs/SPEC.md`, `DESIGN.md`, `TASKS.md` aus dieser Datei
- [ ] `manifest.json`, `hacs.json`, `pyproject.toml`, Frontend-Tooling, Lint, Tests
- [ ] CI (`validate.yml`, `release.yml` mit ZIP, kein Pre-Release)
- [ ] Testinstanz-Config mit Kalendern und Stand-in-Helfern (A4)
- [ ] LICENSE, README-Gerüst (en + de), CHANGELOG; erster Push, CI grün

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
