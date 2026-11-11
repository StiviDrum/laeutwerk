# DESIGN.md – laeutwerk-card

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

## C4. Tokens (wie Zeitwerk)

Immer zuerst HA-Theme-Variablen lesen, Mockup-Wert als Fallback. Einmal auf `:host` definieren.

| Token | Quelle | Fallback |
|---|---|---|
| `--lw-bg` | `--ha-card-background`, `--card-background-color` | `#151518` |
| `--lw-surface` (Pillen, Chips) | `--secondary-background-color` gemischt | `rgba(255,255,255,0.06)` |
| `--lw-border` | `--ha-card-border-color`, `--divider-color` | `rgba(255,255,255,0.08–0.12)` |
| `--lw-text` | `--primary-text-color` | `#f5f5f7` |
| `--lw-text-2` | `--secondary-text-color` | `rgba(245,245,247,0.62)` |
| `--lw-accent` | `--primary-text-color` in dunklen (monochromen) Themes, sonst `--primary-color` | `#f5f5f7` |
| `--lw-ok` | `--success-color` | `#4ad295` |
| `--lw-danger` | `--error-color` | `#ff5a6e` |
| `--lw-radius-card` | `--ha-card-border-radius` | `26px` |
| Schrift | `--ha-font-family-body` / inherit | – |

Referenz-Theme: `docs/reference/claude_glass_theme.yaml`. Komponenten-Maße und Muster (Kopf-Pille 64 px, Symbolkreis 44 px, Trenner, Segmented Control, Dialoge) aus `docs/DESIGN.md` und `frontend/src/styles.ts` des Zeitwerk-Repos übernehmen.

## C5. Barrierefreiheit

- Echte `<button>`s mit `aria-label` bei Symbol-Knöpfen, Touch-Ziele ≥ 44 px.
- Farbe ist nie das einzige Signal: Farbpunkte tragen zusätzlich den Text der Treffer, Status steht als Text im Chip.
