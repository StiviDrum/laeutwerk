/**
 * Rule editor (DESIGN C1.2): six steps in cards – calendar, keyword table
 * (horizontally scrollable) with live preview, reminder times and repeat,
 * signals, acknowledgement, details. Opens the signal editor as a sub page.
 */
import { LitElement, css, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import {
  SIGNAL_ICONS,
  availableVariables,
  badgeLook,
  badgeLooks,
  pluralHeadlinePreview,
  singularHeadlinePreview,
  defaultSignal,
  describeTimespec,
  formatDate,
  relativeDayTime,
  colName,
  colPlural,
  colorNameToHex,
  signalTitle,
  stageColor,
  columnNames,
  errorStep,
  ruleProblems,
  stepSummary,
  translateError,
  type Problem,
  renameColumn,
  ruleComplete,
  setColumnPlural,
  tagVariables,
  templateVariables,
  validTagAcks,
  signalSummary,
  keepOnlySource,
  sourceModeOf,
  type SourceMode,
} from "./format";
import type { Localizer, StringKey } from "./localize";
import { helpTip } from "./help-tip";
import { editKeywordLook } from "./keyword-look";
import { shared, tokens } from "./styles";
import type {
  Acknowledge,
  HaConfig,
  HomeAssistant,
  KeywordRow,
  Badge,
  MatchMode,
  PreviewResult,
  PersonInfo,
  Rotation,
  Rule,
  Signal,
  TitleSuggestion,
} from "./types";

/** Shared empty list: a new [] on every render would look like a new value. */
const EMPTY: never[] = [];

type TimeKind = "days" | "same" | "hours" | "minutes" | "custom";

function errorText(err: unknown): string {
  if (err && typeof err === "object" && "message" in err) return String(err.message);
  return String(err);
}

const PALETTE = [
  "#2f6bff",
  "#2fbf4a",
  "#ffc400",
  "#8a8a94",
  "#ff6b2f",
  "#c58cff",
  "#ff4f8b",
  "#2fd4d4",
];

/** Colour offered for a keyword: from an older colour column, else a palette. */
function suggestColor(row: KeywordRow, index: number, columns: string[]): string {
  const column = ["farbe", "colour"].find((c) => columns.includes(c));
  const named = column && row[column] ? colorNameToHex(String(row[column])) : null;
  return named ?? PALETTE[index % PALETTE.length];
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export class LaeutwerkRuleEditor extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @property({ attribute: false }) public localize!: Localizer;
  /** Rule to edit (a copy is edited); without id it is a new rule. */
  @property({ attribute: false }) public rule!: Rule;
  @state() private _rule!: Rule;
  @state() private _preview?: PreviewResult;
  @state() private _previewError?: string;
  @state() private _error?: string;
  @state() private _saving = false;
  @state() private _signal?: { index: number; signal: Signal };
  @state() private _timeKind: TimeKind = "days";
  @state() private _timeDays = 1;
  @state() private _timeClock = "17:00";
  @state() private _timeAmount = 2;
  @state() private _timeCustom = "";
  @state() private _confirmDelete = false;
  @state() private _exportYaml?: string;
  @state() private _notice?: string;
  /** Steps that are open; new rules are filled in step by step (guided). */
  @state() private _open = new Set<number>();
  @state() private _guided = false;
  @state() private _mode: SourceMode = "calendar";
  /** Persons with their phones (to show push targets by person). */
  @state() private _persons: PersonInfo[] = [];
  @state() private _problems: Problem[] = [];
  @state() private _serverError?: { step?: number; text: string; detail: string };
  @state() private _confirmCancel = false;
  @state() private _draft?: { rule: Rule; saved_at: string };
  @state() private _knownTags?: { id: string; name?: string | null }[];
  @state() private _titles?: TitleSuggestion[];
  /** The keyword table can scroll further to the right (shows an edge fade). */
  @state() private _kwMore = false;
  private _initial = "";
  private _previewTimer?: number;
  private _draftTimer?: number;

  protected willUpdate(changed: PropertyValues): void {
    if (changed.has("rule") && this.rule) {
      const copy = clone(this.rule);
      delete copy.status;
      this._rule = copy;
      this._initial = JSON.stringify(copy);
      this._guided = !copy.id;
      this._mode = sourceModeOf(copy);
      this._open = new Set(copy.id ? [] : [1]);
      this._draft = this._readDraft();
      this._schedulePreview(0);
    }
  }

  public connectedCallback(): void {
    super.connectedCallback();
    if (!this._persons.length && this.hass) {
      this.hass
        .callWS<{ persons: PersonInfo[] }>({ type: "laeutwerk/persons" })
        .then((res) => (this._persons = res.persons))
        .catch(() => undefined);
    }
    if (this._knownTags === undefined && this.hass) {
      this.hass
        .callWS<{ id: string; name?: string | null }[]>({ type: "tag/list" })
        .then((tags) => (this._knownTags = tags))
        .catch(() => (this._knownTags = []));
    }
  }

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    window.clearTimeout(this._previewTimer);
    window.clearTimeout(this._draftTimer);
  }

  // --- draft in the browser (per viewer, best effort) -------------------------

  private get _draftKey(): string {
    return `laeutwerk-draft-${this.rule?.id ?? "new"}`;
  }

  private _readDraft(): { rule: Rule; saved_at: string } | undefined {
    try {
      const raw = window.localStorage.getItem(this._draftKey);
      if (!raw) return undefined;
      const draft = JSON.parse(raw) as { rule: Rule; saved_at: string };
      return JSON.stringify(draft.rule) === this._initial ? undefined : draft;
    } catch {
      return undefined;
    }
  }

  private _storeDraft(): void {
    window.clearTimeout(this._draftTimer);
    this._draftTimer = window.setTimeout(() => {
      try {
        if (this._dirty) {
          window.localStorage.setItem(
            this._draftKey,
            JSON.stringify({ rule: this._rule, saved_at: new Date().toISOString() }),
          );
        } else {
          window.localStorage.removeItem(this._draftKey);
        }
      } catch {
        // storage blocked (private window): no draft
      }
    }, 800);
  }

  private _clearDraft(): void {
    window.clearTimeout(this._draftTimer);
    try {
      window.localStorage.removeItem(this._draftKey);
    } catch {
      // ignore
    }
  }

  private get _dirty(): boolean {
    return JSON.stringify(this._rule) !== this._initial;
  }

  /** Display name of an entity (friendly name, else the id). */
  private _names = (entityId: string): string => {
    if (entityId.startsWith("notify.")) {
      const person = this._persons.find((p) => p.notify.includes(entityId));
      return person ? person.name : entityId.replace(/^notify\./, "");
    }
    return (
      (this.hass?.states[entityId]?.attributes.friendly_name as string | undefined) ?? entityId
    );
  };

  /** Source mode other than calendar (no keyword table, no lookahead). */
  private get _custom(): boolean {
    return this._mode !== "calendar";
  }

  private get _trigger(): boolean {
    return this._mode === "trigger";
  }

  /** Switching keeps exactly one source; the other two are cleared. */
  private _setMode(mode: SourceMode): void {
    if (mode === this._mode) return;
    this._mode = mode;
    const base: Rule = { ...this._rule, sources: [], interval: null, start_triggers: undefined };
    this._rule = { ...keepOnlySource(base, mode), filter: this._rule.filter };
    this._update({}, true);
  }

  /** The rule as it is saved: only the part of the chosen source mode. */
  private _forSaving(rule: Rule): Rule {
    return keepOnlySource(rule, this._mode);
  }

  private _toggleStep(num: number): void {
    const open = new Set(this._open);
    if (open.has(num)) open.delete(num);
    else open.add(num);
    this._open = open;
  }

  private _nextStep(num: number): void {
    const open = new Set(this._open);
    open.delete(num);
    open.add(num + 1);
    this._open = open;
    void this.updateComplete.then(() =>
      this.renderRoot.querySelector(`section[data-step="${num + 1}"]`)?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      }),
    );
  }

  private get _l(): Localizer {
    return this.localize;
  }

  private _update(changes: Partial<Rule>, preview = false): void {
    this._rule = { ...this._rule, ...changes };
    this._confirmCancel = false;
    if (this._problems.length) this._problems = ruleProblems(this._forSaving(this._rule), this._l);
    this._storeDraft();
    if (preview) this._schedulePreview(500);
  }

  private _schedulePreview(delay: number): void {
    window.clearTimeout(this._previewTimer);
    this._previewTimer = window.setTimeout(() => void this._loadPreview(), delay);
  }

  private async _loadPreview(): Promise<void> {
    if (!this.hass || !this._rule?.sources.length || this._custom) {
      this._preview = undefined;
      return;
    }
    const rule = clone(this._rule);
    // Only what decides the matches: other steps may be half filled in and
    // must not turn the preview into an error.
    const season = rule.activation?.season;
    const preview: Record<string, unknown> = {
      sources: rule.sources,
      filter: {
        all_day: rule.filter.all_day,
        keywords: {
          columns: rule.filter.keywords.columns,
          rows: rule.filter.keywords.rows.filter((r) => r.match.trim()),
        },
      },
      bundle: rule.bundle,
      reminders: rule.reminders.length ? rule.reminders : [{ at: "09:00" }],
      expire: rule.expire,
      // Tags with {variables}: the preview shows them resolved.
      acknowledge: validTagAcks(rule),
    };
    if (season?.from && season?.to) preview.activation = { season };
    try {
      this._preview = await this.hass.callWS<PreviewResult>({
        type: "laeutwerk/preview",
        rule: preview,
        limit: 5,
        titles: true,
      });
      this._titles = this._preview.titles;
      this._previewError = undefined;
    } catch (err) {
      this._previewError = errorText(err);
    }
  }

  private _emit(name: "saved" | "cancel" | "deleted", detail?: unknown): void {
    this.dispatchEvent(new CustomEvent(name, { detail }));
  }

  private async _save(): Promise<void> {
    if (!this.hass) return;
    this._error = undefined;
    this._serverError = undefined;
    // Check in the card first: clear messages at the step concerned.
    this._problems = ruleProblems(this._forSaving(this._rule), this._l);
    if (this._problems.length) {
      this._open = new Set([...this._open, ...this._problems.map((p) => p.step)]);
      return;
    }
    this._saving = true;
    const rule = clone(this._forSaving(this._rule));
    try {
      const saved = rule.id
        ? await this.hass.callWS<Rule>({ type: "laeutwerk/rules/update", rule_id: rule.id, rule })
        : await this.hass.callWS<Rule>({ type: "laeutwerk/rules/create", rule });
      this._clearDraft();
      this._emit("saved", saved);
    } catch (err) {
      const detail = errorText(err);
      const step = errorStep(detail);
      this._serverError = { step, text: translateError(detail, this._l), detail };
      if (step) this._open = new Set([...this._open, step]);
    } finally {
      this._saving = false;
    }
  }

  private _cancel(): void {
    if (this._dirty && !this._confirmCancel) {
      this._confirmCancel = true;
      return;
    }
    this._clearDraft();
    this._emit("cancel");
  }

  private async _saveTemplate(): Promise<void> {
    if (!this.hass) return;
    const rule = clone(this._rule);
    delete rule.id;
    rule.filter.keywords.rows = rule.filter.keywords.rows.filter((r) => r.match.trim());
    try {
      await this.hass.callWS({
        type: "laeutwerk/templates/save",
        name: rule.name,
        rule,
      });
      this._notice = this._l.t("template_saved");
    } catch (err) {
      this._error = this._l.t("failed", { error: errorText(err) });
    }
  }

  private async _export(): Promise<void> {
    if (!this.hass || !this._rule.id) return;
    try {
      const res = await this.hass.callWS<{ yaml: string }>({
        type: "laeutwerk/rules/export",
        rule_ids: [this._rule.id],
      });
      this._exportYaml = res.yaml;
    } catch (err) {
      this._error = this._l.t("failed", { error: errorText(err) });
    }
  }

  private async _delete(): Promise<void> {
    if (!this.hass || !this._rule.id) return;
    if (!this._confirmDelete) {
      this._confirmDelete = true;
      return;
    }
    try {
      await this.hass.callWS({ type: "laeutwerk/rules/delete", rule_id: this._rule.id });
      this._emit("deleted", this._rule.id);
    } catch (err) {
      this._error = this._l.t("failed", { error: errorText(err) });
    }
  }

  // --- keyword table ----------------------------------------------------------

  /** Keyword colours offered as swatches in every colour popup. */
  private _kwSwatches(): { label: string; color: string }[] {
    // Own keyword colour, else a colour from an older "farbe"/"colour" column.
    const columns = this._rule.filter.keywords.columns ?? [];
    const column = ["farbe", "colour"].find((c) => columns.includes(c));
    return this._rule.filter.keywords.rows
      .map((r) => ({
        label: String(r.match),
        color: r.color ?? (column && r[column] ? colorNameToHex(String(r[column])) : null),
      }))
      .filter((s): s is { label: string; color: string } => !!s.color);
  }

  private _setRows(rows: KeywordRow[]): void {
    const keywords = { ...this._rule.filter.keywords, rows };
    this._update({ filter: { ...this._rule.filter, keywords } }, true);
  }

  private _setRow(index: number, changes: Partial<KeywordRow>): void {
    this._setRows(
      this._rule.filter.keywords.rows.map((row, i) => {
        if (i !== index) return row;
        const next = { ...row, ...changes } as KeywordRow;
        if (next.mode === "contains") delete next.mode;
        return next;
      }),
    );
  }

  /** An older text column with colour names whose rows have no colour yet. */
  private _colorColumn(): string | undefined {
    const names = columnNames(this._rule);
    const column = ["farbe", "colour"].find((c) => names.includes(c));
    if (!column) return undefined;
    const rows = this._rule.filter.keywords.rows;
    return rows.some((r) => !r.color && r[column] && colorNameToHex(String(r[column])))
      ? column
      : undefined;
  }

  private _takeColumnColors(): void {
    const column = this._colorColumn();
    if (!column) return;
    this._setRows(
      this._rule.filter.keywords.rows.map((r) =>
        r.color || !r[column] ? r : { ...r, color: colorNameToHex(String(r[column])) ?? undefined },
      ),
    );
  }

  private _addColumn(): void {
    const { columns, rows } = this._rule.filter.keywords;
    const names = columns.map(colName);
    let name = "spalte";
    for (let n = 2; names.includes(name); n++) name = `spalte${n}`;
    const keywords = {
      columns: [...columns, name],
      rows: rows.map((r) => ({ ...r, [name]: "" })),
    };
    this._update({ filter: { ...this._rule.filter, keywords } });
  }

  private _removeColumn(index: number): void {
    const { columns, rows } = this._rule.filter.keywords;
    const name = colName(columns[index]);
    const keywords = {
      columns: columns.filter((_, i) => i !== index),
      rows: rows.map((r) => {
        const next = { ...r };
        delete next[name];
        return next;
      }),
    };
    const signals = this._rule.signals.map((s) =>
      s.color_from === name ? { ...s, color_from: undefined } : s,
    );
    this._update({ signals, filter: { ...this._rule.filter, keywords } }, true);
  }

  // --- times ------------------------------------------------------------------

  private _newTime(): string {
    const clock = this._timeClock || "17:00";
    switch (this._timeKind) {
      case "days":
        return `-${Math.max(1, this._timeDays)}d ${clock}`;
      case "same":
        return clock;
      case "hours":
        return `-${Math.max(1, this._timeAmount)}h`;
      case "minutes":
        return `-${Math.max(1, this._timeAmount)}m`;
      default:
        return this._timeCustom.trim();
    }
  }

  private _addTime(): void {
    const at = this._newTime();
    if (!at || this._rule.reminders.some((r) => r.at === at)) return;
    this._update({ reminders: [...this._rule.reminders, { at }] });
  }

  // --- signals ------------------------------------------------------------------

  private _openSignal(index: number, signal?: Signal): void {
    const target = signal ?? this._rule.signals[index];
    this._signal = { index, signal: clone(target) };
  }

  private _applySignal(ev: CustomEvent<{ signal: Signal }>): void {
    if (!this._signal) return;
    const signals = [...this._rule.signals];
    signals[this._signal.index] = ev.detail.signal;
    this._update({ signals });
    this._signal = undefined;
  }

  private _deleteSignal(): void {
    if (!this._signal) return;
    this._update({ signals: this._rule.signals.filter((_, i) => i !== this._signal!.index) });
    this._signal = undefined;
  }

  private _setAck(acknowledge: Acknowledge[]): void {
    this._update({ acknowledge });
  }

  // --- render ---------------------------------------------------------------

  protected render() {
    if (!this._rule) return nothing;
    if (this._signal) {
      return html`<laeutwerk-signal-editor
        .hass=${this.hass}
        .localize=${this._l}
        .rule=${this._rule}
        .signal=${this._signal.signal}
        .sample=${this._preview?.events[0]?.variables ?? {}}
        .ruleId=${this.rule.id}
        .swatches=${[...new Set((this._preview?.events ?? []).flatMap((e) => e.colors))]}
        @apply=${this._applySignal}
        @cancel=${() => (this._signal = undefined)}
        @delete=${this._deleteSignal}
      ></laeutwerk-signal-editor>`;
    }
    const l = this._l;
    const valid = ruleComplete(this._forSaving(this._rule));
    return html`<div class="page">
      <div class="separator">
        ${this._rule.id ? l.t("edit_rule") : l.t("new_rule")}<span class="line"></span>
      </div>
      ${
        this._draft
          ? html`<div class="panel draft">
              <div class="hint">
                ${l.t("draft_found", {
                  when: relativeDayTime(
                    this._draft.saved_at,
                    new Date(),
                    l,
                    this.hass?.config?.time_zone,
                  ),
                })}
              </div>
              <div class="wrap">
                <button
                  class="chip accent"
                  @click=${() => {
                    this._rule = this._draft!.rule;
                    this._draft = undefined;
                    this._open = new Set([1, 2, 3, 4, 5, 6, 7]);
                    this._schedulePreview(0);
                  }}
                >
                  ${l.t("draft_restore")}
                </button>
                <button
                  class="chip"
                  @click=${() => {
                    this._draft = undefined;
                    this._clearDraft();
                  }}
                >
                  ${l.t("draft_discard")}
                </button>
              </div>
            </div>`
          : nothing
      }
      ${this._stepCalendar()} ${this._custom ? nothing : this._stepEvents()} ${this._stepWhen()}
      ${this._stepSignals()} ${this._stepAck()} ${this._stepDetails()} ${this._stepAdvanced()}
      ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
      ${
        this._serverError && !this._serverError.step
          ? this._errorBox(this._serverError.text, this._serverError.detail)
          : nothing
      }
      ${
        this._problems.length
          ? html`<div class="error">
              ${l.t("problems_title")} ${this._problems.map((p) => p.text).join(" ")}
            </div>`
          : nothing
      }
      ${
        this._exportYaml !== undefined
          ? html`<div class="panel">
              <div class="step">${l.t("export")}</div>
              <div class="hint">${l.t("export_hint")}</div>
              <textarea class="yaml" readonly .value=${this._exportYaml}></textarea>
            </div>`
          : nothing
      }
      <div class="row extra">
        <button class="chip" ?disabled=${!valid} @click=${this._saveTemplate}>
          <ha-icon icon="mdi:content-save-outline"></ha-icon>${l.t("save_as_template")}
        </button>
        ${
          this._rule.id
            ? html`<button class="chip" @click=${this._export}>
                <ha-icon icon="mdi:export"></ha-icon>${l.t("export")}
              </button>`
            : nothing
        }
        <span class="hint grow">${this._notice ?? ""}</span>
      </div>
      ${
        this._rule.id
          ? html`<button class="pill danger wide" @click=${this._delete}>
              ${this._confirmDelete ? l.t("confirm_delete") : l.t("delete_rule")}
            </button>`
          : nothing
      }
      <div class="actions">
        <button class="pill outline ${this._confirmCancel ? "danger" : ""}" @click=${this._cancel}>
          ${this._confirmCancel ? l.t("discard_changes") : l.t("cancel")}
        </button>
        <button class="pill primary" ?disabled=${this._saving} @click=${this._save}>
          ${this._saving ? "…" : l.t("save")}
        </button>
      </div>
    </div>`;
  }

  private _errorBox(text: string, detail: string): TemplateResult {
    return html`<div class="error">
      ${text}
      ${
        detail !== text
          ? html`<details>
              <summary>${this._l.t("error_detail")}</summary>
              <code>${detail}</code>
            </details>`
          : nothing
      }
    </div>`;
  }

  private _step(num: number, title: StringKey, body: TemplateResult): TemplateResult {
    const l = this._l;
    const open = this._open.has(num);
    const problems = this._problems.filter((p) => p.step === num);
    const server = this._serverError?.step === num ? this._serverError : undefined;
    const issues = problems.length + (server ? 1 : 0);
    const names = (id: string) =>
      (this.hass?.states[id]?.attributes.friendly_name as string | undefined) ?? id;
    return html`<section class="panel ${issues ? "has-error" : ""}" data-step=${num}>
      <button class="step head" aria-expanded=${open} @click=${() => this._toggleStep(num)}>
        <span class="num">${this._custom && num > 2 ? num - 1 : num}</span>
        <span class="grow text">
          <span>${l.t(title)}</span>
          ${
            open
              ? nothing
              : html`<span class="summary">${stepSummary(this._rule, num, l, names)}</span>`
          }
        </span>
        ${issues ? html`<span class="badge">${issues}</span>` : nothing}
        <ha-icon .icon=${open ? "mdi:chevron-up" : "mdi:chevron-down"}></ha-icon>
      </button>
      ${
        open
          ? html`${problems.map((p) => html`<div class="error">${p.text}</div>`)}
            ${server ? this._errorBox(server.text, server.detail) : nothing} ${body}
            ${
              this._guided && num < 7
                ? html`<button class="pill outline next" @click=${() => this._nextStep(num)}>
                    ${l.t("next_step")}<ha-icon icon="mdi:chevron-down"></ha-icon>
                  </button>`
                : nothing
            }`
          : nothing
      }
    </section>`;
  }

  private _stepCalendar(): TemplateResult {
    const l = this._l;
    const r = this._rule;
    return this._step(
      1,
      "step_calendar",
      html`
        <label class="field"
          >${l.t("name")}
          <input
            .value=${r.name}
            placeholder=${l.t("name_placeholder")}
            @input=${(e: Event) => this._update({ name: (e.target as HTMLInputElement).value })}
          />
        </label>
        <div class="row">
          <laeutwerk-field
            class="grow"
            .hass=${this.hass}
            .localize=${l}
            .label=${l.t("icon")}
            .selector=${{ icon: {} }}
            .value=${r.icon ?? ""}
            @value-changed=${(e: CustomEvent<{ value: string }>) =>
              this._update({ icon: e.detail.value || null })}
          ></laeutwerk-field>
          <laeutwerk-field
            class="colorfield"
            .hass=${this.hass}
            .localize=${l}
            .label=${l.t("color")}
            .selector=${{ color_rgb: {} }}
            .swatches=${this._kwSwatches()}
            .value=${r.color ?? ""}
            @value-changed=${(e: CustomEvent<{ value: string }>) =>
              this._update({ color: e.detail.value || null })}
          ></laeutwerk-field>
        </div>
        <div class="sublabel tiprow">${l.t("source_mode")}${helpTip(l, "help_step_calendar")}</div>
        <div class="segmented">
          ${(
            [
              ["calendar", "source_calendar"],
              ["trigger", "source_trigger"],
              ["interval", "source_custom"],
            ] as const
          ).map(
            ([mode, key]) =>
              html`<button aria-pressed=${this._mode === mode} @click=${() => this._setMode(mode)}>
                ${l.t(key)}
              </button>`,
          )}
        </div>
        ${
          this._trigger
            ? this._triggerFields()
            : this._custom
              ? this._intervalFields()
              : this._sourceFields()
        }
      `,
    );
  }

  /** Calendar mode: calendars, to-do lists and date entities. */
  private _sourceFields(): TemplateResult {
    const l = this._l;
    const r = this._rule;
    return html`
      <laeutwerk-field
        .hass=${this.hass}
        .localize=${l}
        .label=${l.t("sources")}
        .selector=${{
          entity: {
            domain: ["calendar", "todo", "date", "datetime", "input_datetime", "sensor"],
            multiple: true,
          },
        }}
        .value=${r.sources}
        @value-changed=${(e: CustomEvent<{ value: string[] | string }>) => {
          const value = e.detail.value;
          this._update({ sources: Array.isArray(value) ? value : value ? [value] : [] }, true);
        }}
      ></laeutwerk-field>
      ${
        r.sources.some((id) => id.startsWith("calendar."))
          ? html`<label class="field">
              <span class="tiprow">${l.t("lookahead")}${helpTip(l, "help_lookahead")}</span>
              <input
                type="number"
                min="1"
                max="365"
                .value=${String(r.lookahead_days ?? 14)}
                @change=${(e: Event) => {
                  const n = Math.round(Number((e.target as HTMLInputElement).value));
                  this._update({ lookahead_days: Math.min(365, Math.max(1, n || 14)) });
                }}
              />
            </label>`
          : nothing
      }
    `;
  }

  /** Trigger mode: the reminder starts when one of the triggers fires. */
  private _triggerFields(): TemplateResult {
    const l = this._l;
    return html`
      <div class="sublabel">${l.t("trigger_start")}</div>
      <laeutwerk-field
        .hass=${this.hass}
        .localize=${l}
        .selector=${{ trigger: {} }}
        .value=${this._rule.start_triggers ?? EMPTY}
        @value-changed=${(e: CustomEvent<{ value: HaConfig[] | HaConfig | undefined }>) => {
          const v = e.detail.value;
          this._update({ start_triggers: Array.isArray(v) ? v : v ? [v] : [] });
        }}
      ></laeutwerk-field>
    `;
  }

  /** Interval mode: due again n days after it was last done. */
  private _intervalFields(): TemplateResult {
    const l = this._l;
    const interval = this._rule.interval ?? { every: 90 };
    return html`
      <div class="row">
        <label class="field grow"
          >${l.t("interval_days")}
          <input
            type="number"
            min="1"
            .value=${String(interval.every)}
            @change=${(e: Event) =>
              this._update({
                interval: { ...interval, every: Number((e.target as HTMLInputElement).value) },
              })}
          />
        </label>
        <label class="field grow"
          >${l.t("interval_start")}
          <input
            type="date"
            .value=${interval.start ?? ""}
            @change=${(e: Event) => {
              const start = (e.target as HTMLInputElement).value;
              const next: { every: number | string; start?: string } = { every: interval.every };
              if (start) next.start = start;
              this._update({ interval: next });
            }}
          />
        </label>
      </div>
    `;
  }

  /** Round preview of a keyword's icon in its colour (with the rule as fallback). */
  private _kwBadge(row: KeywordRow, columns: string[], size = 36): TemplateResult {
    const named = ["farbe", "colour"].find((c) => columns.includes(c));
    const look = badgeLook(this._rule, {
      icon: row.icon ?? null,
      color: row.color ?? (named && row[named] ? colorNameToHex(String(row[named])) : null),
    });
    const color = look.color ?? "var(--lw-text-2)";
    return html`<span
      class="kwbadge"
      style="width:${size}px;height:${size}px;background: color-mix(in srgb, ${color} 22%, transparent); color: ${color}"
      ><ha-icon .icon=${look.icon}></ha-icon
    ></span>`;
  }

  /** Up to three small badges of a preview hit. */
  private _hitBadges(event: { badges?: Badge[]; colors?: string[] }): TemplateResult {
    const looks = badgeLooks(this._rule, event).slice(0, 3);
    return html`<span class="hitbadges">
      ${looks.map((look) => {
        const color = look.color ?? "var(--lw-text-2)";
        return html`<span
          class="kwbadge"
          style="width:28px;height:28px;background: color-mix(in srgb, ${color} 22%, transparent); color: ${color}"
          ><ha-icon .icon=${look.icon}></ha-icon
        ></span>`;
      })}
    </span>`;
  }

  private _stepEvents(): TemplateResult {
    const l = this._l;
    const { columns: specs, rows } = this._rule.filter.keywords;
    const columns = specs.map(colName);
    return this._step(
      2,
      "step_events",
      html`
        ${this._toggle(
          l.t("only_all_day"),
          this._rule.filter.all_day,
          (v) => this._update({ filter: { ...this._rule.filter, all_day: v } }, true),
          "help_all_day",
        )}
        <div class="sublabel tiprow">${l.t("keywords_label")}${helpTip(l, "help_keywords")}</div>
        <div class="kwwrap ${this._kwMore ? "more" : ""}">
          <div class="kwtable" role="table" @scroll=${this._kwScroll}>
            <div class="kwinner">
              <div class="kwrow head" role="row">
                <div class="stick hcell" role="columnheader">
                  ${l.t("keyword")}${helpTip(l, "help_icon_color")}
                </div>
                <div class="c-mode hcell" role="columnheader">${l.t("match_mode")}</div>
                ${specs.map((spec, i) => {
                  const plural = colPlural(spec);
                  return html`<div class="c-var hcell" role="columnheader">
                    <div class="vhead">
                      <input
                        class="vname"
                        .value=${colName(spec)}
                        aria-label=${l.t("column_name")}
                        @change=${(e: Event) =>
                          this._update(
                            renameColumn(this._rule, i, (e.target as HTMLInputElement).value),
                            true,
                          )}
                      />
                      <button
                        class="plural"
                        role="switch"
                        aria-checked=${!!plural}
                        title=${plural ? `${l.t("plural_toggle")}: {${plural}}` : l.t("plural_toggle")}
                        aria-label=${l.t("plural_toggle")}
                        @click=${() => this._update(setColumnPlural(this._rule, i, !plural))}
                      >
                        n
                      </button>
                      <button
                        class="x"
                        aria-label=${l.t("remove")}
                        @click=${() => this._removeColumn(i)}
                      >
                        <ha-icon icon="mdi:close"></ha-icon>
                      </button>
                    </div>
                  </div>`;
                })}
              </div>
              ${rows.map(
                (row, i) =>
                  html`<div class="kwrow" role="row">
                    <div class="stick" role="cell">
                      <button
                        class="lookbtn"
                        aria-label=${l.t("kw_look_edit")}
                        title=${l.t("kw_look_edit")}
                        @click=${() => this._editLook(i, columns)}
                      >
                        ${this._kwBadge(row, columns, 38)}
                        ${
                          row.icon || row.color
                            ? nothing
                            : html`<span class="plusdot"><ha-icon icon="mdi:plus"></ha-icon></span>`
                        }
                      </button>
                      <input
                        class="kwinput"
                        .value=${row.match}
                        aria-label=${l.t("keyword")}
                        @input=${(e: Event) => this._setRow(i, { match: (e.target as HTMLInputElement).value })}
                      />
                    </div>
                    <div class="c-mode" role="cell">
                      <select
                        aria-label=${l.t("match_mode")}
                        @change=${(e: Event) =>
                          this._setRow(i, {
                            mode: (e.target as HTMLSelectElement).value as MatchMode,
                          })}
                      >
                        ${(["contains", "startswith", "regex"] as const).map(
                          (m) =>
                            html`<option value=${m} ?selected=${(row.mode ?? "contains") === m}>
                              ${l.t(`mode_${m}` as StringKey)}
                            </option>`,
                        )}
                      </select>
                    </div>
                    ${columns.map(
                      (c) =>
                        html`<div class="c-var" role="cell">
                          ${
                            /nfc|tag/i.test(c)
                              ? html`<laeutwerk-suggest
                                  .items=${this._tagItems()}
                                  .value=${row[c] ?? ""}
                                  .placeholder=${l.t("tag_suggest_placeholder")}
                                  @value-changed=${(e: CustomEvent<{ value: string }>) =>
                                    this._setRow(i, { [c]: e.detail.value })}
                                ></laeutwerk-suggest>`
                              : html`<input
                                  .value=${row[c] ?? ""}
                                  aria-label=${c}
                                  @input=${(e: Event) => this._setRow(i, { [c]: (e.target as HTMLInputElement).value })}
                                />`
                          }
                        </div>`,
                    )}
                  </div>`,
              )}
            </div>
          </div>
        </div>
        <div class="wrap">
          <button
            class="addbtn"
            @click=${() =>
              this._setRows([
                ...rows,
                { match: "", ...Object.fromEntries(columns.map((c) => [c, ""])) },
              ])}
          >
            <ha-icon icon="mdi:plus"></ha-icon>${l.t("add_keyword")}
          </button>
          <button class="addbtn" @click=${this._addColumn}>
            <ha-icon icon="mdi:plus"></ha-icon>${l.t("add_column")}
          </button>
          ${helpTip(l, "help_plural")}
          ${
            this._colorColumn()
              ? html`<button class="addbtn accent" @click=${this._takeColumnColors}>
                  <ha-icon icon="mdi:palette-outline"></ha-icon>${l.t("colors_from_column", {
                    column: this._colorColumn()!,
                  })}
                </button>`
              : nothing
          }
        </div>
        ${!rows.length ? html`<div class="hint">${l.t("no_keywords")}</div>` : nothing}
        ${this._suggestions()} ${this._previewList()}
      `,
    );
  }

  private _kwScroll = (): void => {
    const el = this.renderRoot.querySelector<HTMLElement>(".kwtable");
    if (!el) return;
    const more = el.scrollWidth - el.scrollLeft - el.clientWidth > 4;
    if (more !== this._kwMore) this._kwMore = more;
  };

  protected updated(): void {
    this._kwScroll();
  }

  /** Open the icon/colour popup of keyword row `index`. */
  private async _editLook(index: number, columns: string[]): Promise<void> {
    const row = this._rule.filter.keywords.rows[index];
    if (!row) return;
    const result = await editKeywordLook({
      hass: this.hass,
      localize: this._l,
      title: row.match || this._l.t("keyword"),
      icon: row.icon ?? "",
      color: row.color ?? "",
      rule: this._rule,
      swatches: this._kwSwatches(),
      suggest: suggestColor(row, index, columns),
      dark: !!this.hass?.themes?.darkMode,
    });
    if (result === "delete") {
      this._setRows(this._rule.filter.keywords.rows.filter((_, j) => j !== index));
    } else if (result) {
      this._setRow(index, { icon: result.icon || undefined, color: result.color || undefined });
    }
  }

  /** Known NFC tags as suggestion items. */
  private _tagItems(): { value: string; label?: string }[] {
    return (this._knownTags ?? []).map((tag) => ({ value: tag.id, label: tag.name ?? undefined }));
  }

  private _suggestions(): TemplateResult | typeof nothing {
    const open = (this._titles ?? []).filter((t) => !t.matched);
    if (!open.length) return nothing;
    const l = this._l;
    const columns = columnNames(this._rule);
    const add = (titles: string[]) =>
      this._setRows([
        ...this._rule.filter.keywords.rows,
        ...titles.map((title) => ({
          match: title,
          ...Object.fromEntries(columns.map((c) => [c, ""])),
        })),
      ]);
    return html`<div class="sublabel">${l.t("suggestions")}</div>
      <div class="wrap">
        ${open.map(
          (t) =>
            html`<button class="chip dashed" @click=${() => add([t.title])}>
              <ha-icon icon="mdi:plus"></ha-icon>${t.title}${t.count > 1 ? ` · ${t.count}×` : ""}
            </button>`,
        )}
        ${
          open.length > 1
            ? html`<button class="chip accent" @click=${() => add(open.map((t) => t.title))}>
                ${l.t("suggestions_all")}
              </button>`
            : nothing
        }
      </div>`;
  }

  private _previewList(): TemplateResult {
    const l = this._l;
    if (this._previewError) return html`<div class="error">${this._previewError}</div>`;
    const preview = this._preview;
    if (!preview) return html``;
    const tz = this.hass?.config?.time_zone;
    const errors = Object.entries(preview.errors);
    return html`
      <div class="sublabel">${l.t("preview")}</div>
      ${errors.map(([entity, error]) => html`<div class="error">${entity}: ${error}</div>`)}
      ${
        preview.events.length
          ? html`<div class="divided">
              ${preview.events.map(
                (e) =>
                  html`<div class="prev">
                    <span class="date">${formatDate(e.start, l, tz)}</span>
                    ${this._hitBadges(e)}
                    <span class="grow">${e.titles.join(" + ")}</span>
                    ${
                      e.titles.length > 1
                        ? html`<span class="chip accent">${l.t("preview_bundled")}</span>`
                        : nothing
                    }
                  </div>`,
              )}
            </div>`
          : html`<div class="hint">${l.t("preview_none")}</div>`
      }
    `;
  }

  private _stepWhen(): TemplateResult {
    const l = this._l;
    const r = this._rule;
    const repeat = r.repeat === "none" ? "none" : "repeat";
    const first = this._preview?.events[0]?.reminder_times?.[0];
    const now = new Date();
    return this._step(
      3,
      "step_when",
      html`
        ${
          this._trigger
            ? nothing
            : html`<div class="sublabel head tiprow">
                  ${l.t("times_label")}${helpTip(l, "help_reminders")}
                </div>
                <div class="wrap">
                  ${r.reminders.map(
                    (item, i) =>
                      html`<span class="chip accent">
                        ${describeTimespec(item.at, l)}
                        <button
                          class="x small"
                          aria-label=${l.t("remove")}
                          @click=${() => this._update({ reminders: r.reminders.filter((_, j) => j !== i) })}
                        >
                          <ha-icon icon="mdi:close"></ha-icon>
                        </button>
                      </span>`,
                  )}
                </div>
                <div class="row addtime">
                  <select
                    @change=${(e: Event) => (this._timeKind = (e.target as HTMLSelectElement).value as TimeKind)}
                  >
                    ${(
                      [
                        ["days", "time_days_before"],
                        ["same", "time_same_day"],
                        ["hours", "time_hours_before"],
                        ["minutes", "time_minutes_before"],
                        ["custom", "time_custom"],
                      ] as const
                    ).map(
                      ([kind, key]) =>
                        html`<option value=${kind} ?selected=${this._timeKind === kind}>
                          ${l.t(key)}
                        </option>`,
                    )}
                  </select>
                  ${
                    this._timeKind === "days"
                      ? html`<input
                          type="number"
                          min="1"
                          .value=${String(this._timeDays)}
                          @input=${(e: Event) => (this._timeDays = Number((e.target as HTMLInputElement).value))}
                        />`
                      : nothing
                  }
                  ${
                    this._timeKind === "days" || this._timeKind === "same"
                      ? html`<input
                          type="time"
                          .value=${this._timeClock}
                          @input=${(e: Event) => (this._timeClock = (e.target as HTMLInputElement).value)}
                        />`
                      : this._timeKind === "custom"
                        ? html`<input
                            class="grow"
                            placeholder="-1d 17:00"
                            .value=${this._timeCustom}
                            @input=${(e: Event) => (this._timeCustom = (e.target as HTMLInputElement).value)}
                          />`
                        : html`<input
                            type="number"
                            min="1"
                            .value=${String(this._timeAmount)}
                            @input=${(e: Event) => (this._timeAmount = Number((e.target as HTMLInputElement).value))}
                          />`
                  }
                  <button class="chip dashed" @click=${this._addTime}>
                    <ha-icon icon="mdi:plus"></ha-icon>${l.t("add_time")}
                  </button>
                </div>
                ${
                  first
                    ? html`<div class="hint">
                        ${l.t("reminder_at", { when: relativeDayTime(first, now, l, this.hass?.config?.time_zone) })}
                      </div>`
                    : nothing
                }
                <hr class="sep" />`
        }
        <div class="sublabel head tiprow">${l.t("repeat")}${helpTip(l, "help_repeat")}</div>
        <div class="segmented">
          <button
            aria-pressed=${repeat === "none"}
            @click=${() => this._update({ repeat: "none" })}
          >
            ${l.t("repeat_once")}
          </button>
          <button
            aria-pressed=${repeat === "repeat"}
            @click=${() => repeat !== "repeat" && this._update({ repeat: { every: 60, max: 24 } })}
          >
            ${l.t("repeat_repeat")}
          </button>
        </div>
        ${
          r.repeat !== "none"
            ? html`<div class="row">
                <label class="field grow"
                  >${l.t("repeat_every")}
                  <input
                    type="number"
                    min="1"
                    .value=${String(r.repeat.every)}
                    @change=${(e: Event) =>
                      this._update({
                        repeat: {
                          ...(r.repeat as { every: number }),
                          every: Number((e.target as HTMLInputElement).value),
                        },
                      })}
                  />
                </label>
                <label class="field grow"
                  >${l.t("repeat_max")}
                  <input
                    type="number"
                    min="1"
                    .value=${String(r.repeat.max ?? 24)}
                    @change=${(e: Event) =>
                      this._update({
                        repeat: {
                          ...(r.repeat as { every: number }),
                          max: Number((e.target as HTMLInputElement).value),
                        },
                      })}
                  />
                </label>
              </div>`
            : nothing
        }
      `,
    );
  }

  private _stepSignals(): TemplateResult {
    const l = this._l;
    const signals = this._rule.signals;
    return this._step(
      4,
      "step_signals",
      html`
        <div class="sublabel tiprow">${l.t("signals_label")}${helpTip(l, "help_signals")}</div>
        ${signals.length ? nothing : html`<div class="hint">${l.t("no_signals")}</div>`}
        <div class="divided">
          ${signals.map((s, i) => {
            const color = stageColor(this._rule, s.stage);
            return html`<div class="sig" style=${color ? `--stage: ${color}` : ""}>
              <button class="sigmain" @click=${() => this._openSignal(i)}>
                <span class="icon small ${color ? "staged" : ""}"
                  ><ha-icon .icon=${SIGNAL_ICONS[s.type]}></ha-icon
                ></span>
                <span class="grow">
                  <span class="name">${signalTitle(s, l, this._names)}</span>
                  <span class="sub">
                    ${
                      color
                        ? html`<span class="stagechip">${l.t("stage_n", { n: s.stage! })}</span>`
                        : nothing
                    }
                    ${signalSummary(s, l)}
                  </span>
                </span>
              </button>
              <button
                class="switch"
                role="switch"
                aria-checked=${s.enabled}
                aria-label=${l.t(`type_${s.type}` as StringKey)}
                @click=${() =>
                  this._update({
                    signals: signals.map((x, j) => (j === i ? { ...x, enabled: !x.enabled } : x)),
                  })}
              >
                <span></span>
              </button>
            </div>`;
          })}
        </div>
        <div class="wrap">
          ${(["notify", "light_signal", "announce", "action"] as const).map(
            (type) =>
              html`<button
                class="chip dashed"
                @click=${() => this._openSignal(signals.length, defaultSignal(type, this._rule, l.t("done")))}
              >
                <ha-icon .icon=${SIGNAL_ICONS[type]}></ha-icon>${l.t(`type_${type}` as StringKey)}
              </button>`,
          )}
        </div>
      `,
    );
  }

  private _stepAck(): TemplateResult {
    const l = this._l;
    const acks = this._rule.acknowledge;
    const pushDone = this._rule.signals.some(
      (s) => s.type === "notify" && (s.actions ?? []).some((a) => (a as { ack?: boolean }).ack),
    );
    const tags = this.hass ? Object.values(this.hass.states) : [];
    const lastScan = (tagId: string) =>
      tags.find((s) => s.entity_id.startsWith("tag.") && s.attributes.tag_id === tagId)?.state;
    const setAt = (i: number, changes: Partial<Acknowledge> | null) =>
      this._setAck(
        acks
          .map((a, j) => (j === i ? (changes ? { ...a, ...changes } : null) : a))
          .filter((a): a is Acknowledge => !!a),
      );
    return this._step(
      5,
      "step_ack",
      html`
        <div class="sublabel tiprow">${l.t("ack_head")}${helpTip(l, "help_ack")}</div>
        <div class="divided">
          <div class="ackrow">
            <ha-icon icon="mdi:cellphone-check"></ha-icon>
            <span class="grow">${pushDone ? l.t("ack_push") : l.t("ack_push_none")}</span>
          </div>
          ${acks.map((a, i) => {
            if (a.type === "notify_action") return nothing;
            if (a.type === "tag") {
              const scanned = a.tag_id ? lastScan(a.tag_id) : undefined;
              return html`<div class="ackrow">
                <ha-icon icon="mdi:nfc-variant"></ha-icon>
                <div class="grow">
                  <laeutwerk-suggest
                    .value=${a.tag_id ?? ""}
                    .placeholder=${l.t("ack_tag_placeholder")}
                    .items=${this._tagItems()}
                    .variables=${tagVariables(this._rule)}
                    @value-changed=${(e: CustomEvent<{ value: string }>) =>
                      setAt(i, { tag_id: e.detail.value })}
                    @change=${() => this._schedulePreview(300)}
                  ></laeutwerk-suggest>
                  ${
                    templateVariables(a.tag_id).length
                      ? html`<div class="hint">
                          ${
                            this._preview?.events[0]?.tags?.length
                              ? l.t("tag_next", { tags: this._preview.events[0].tags.join(", ") })
                              : l.t("tag_variable_hint")
                          }
                        </div>`
                      : nothing
                  }
                  ${
                    scanned && scanned !== "unknown"
                      ? html`<div class="hint">
                          ${relativeDayTime(scanned, new Date(), l, this.hass?.config?.time_zone)}
                        </div>`
                      : nothing
                  }
                </div>
                <button class="mini" aria-label=${l.t("remove")} @click=${() => setAt(i, null)}>
                  <ha-icon icon="mdi:close"></ha-icon>
                </button>
              </div>`;
            }
            return html`<div class="ackblock">
              <div class="ackrow">
                <ha-icon icon="mdi:door-open"></ha-icon>
                <span class="grow">${l.t("ack_trigger")}</span>
                <button class="mini" aria-label=${l.t("remove")} @click=${() => setAt(i, null)}>
                  <ha-icon icon="mdi:close"></ha-icon>
                </button>
              </div>
              <laeutwerk-field
                .hass=${this.hass}
                .localize=${l}
                .selector=${{ trigger: {} }}
                .value=${Array.isArray(a.trigger) ? a.trigger : a.trigger ? [a.trigger] : []}
                @value-changed=${(e: CustomEvent<{ value: HaConfig[] }>) => setAt(i, { trigger: e.detail.value })}
              ></laeutwerk-field>
              ${this._toggle(l.t("ack_early"), !!a.early, (v) => setAt(i, { early: v }))}
            </div>`;
          })}
        </div>
        <div class="wrap">
          <button
            class="chip dashed"
            @click=${() => this._setAck([...acks, { type: "tag", tag_id: "" }])}
          >
            <ha-icon icon="mdi:plus"></ha-icon>${l.t("add_tag")}
          </button>
          <button
            class="chip dashed"
            @click=${() => this._setAck([...acks, { type: "trigger", trigger: [], early: false }])}
          >
            <ha-icon icon="mdi:plus"></ha-icon>${l.t("add_trigger")}
          </button>
        </div>
      `,
    );
  }

  private _previewLine(text: string, hint = ""): TemplateResult {
    return html`<div class="preview">
      <ha-icon icon="mdi:eye-outline"></ha-icon><span>${text}</span>${
        hint ? html`<span class="muted">${hint}</span>` : nothing
      }
    </div>`;
  }

  private _singularPreview(): TemplateResult | typeof nothing {
    const text = singularHeadlinePreview(this._rule, this._preview?.events);
    return text ? this._previewLine(text) : nothing;
  }

  private _pluralPreview(): TemplateResult {
    const l = this._l;
    const line = pluralHeadlinePreview(
      this._rule,
      this._preview?.events,
      this._preview?.plural_sample,
    );
    if (!line.text) return html`<div class="muted">${l.t("headline_no_preview")}</div>`;
    return this._previewLine(line.text, line.fallback ? ` ${l.t("headline_same")}` : "");
  }

  private _stepDetails(): TemplateResult {
    const l = this._l;
    const r = this._rule;
    const expire = r.expire.trim();
    const dayMatch = /^event_day (\d{1,2}:\d{2})$/.exec(expire);
    const kind = expire === "event_end" ? "end" : dayMatch ? "day" : "custom";
    return this._step(
      6,
      "step_details",
      html`
        ${
          this._trigger
            ? nothing
            : this._toggle(
                l.t("bundle"),
                r.bundle,
                (v) => this._update({ bundle: v }, true),
                "help_bundle",
              )
        }
        ${this._toggle(
          l.t("visible"),
          r.visible !== false,
          (v) => this._update({ visible: v }),
          "help_visible",
        )}
        <hr class="sep" />
        <div class="sublabel head tiprow">${l.t("headline")}${helpTip(l, "help_headline")}</div>
        ${this._trigger ? nothing : html`<div class="sublabel">${l.t("headline_one")}</div>`}
        <laeutwerk-suggest
          .value=${r.headline ?? ""}
          .placeholder=${l.t("headline_default")}
          .variables=${availableVariables(r)}
          @value-changed=${(e: CustomEvent<{ value: string }>) =>
            this._update({ headline: e.detail.value || null })}
        ></laeutwerk-suggest>
        ${this._singularPreview()}
        ${
          this._trigger
            ? nothing
            : html`<div class="sublabel">${l.t("headline_plural")}</div>
                <laeutwerk-suggest
                  .value=${r.headline_plural ?? ""}
                  .placeholder=${r.headline || l.t("headline_default")}
                  .variables=${availableVariables(r)}
                  @value-changed=${(e: CustomEvent<{ value: string }>) =>
                    this._update({ headline_plural: e.detail.value || null })}
                ></laeutwerk-suggest>
                ${this._pluralPreview()}`
        }
        <hr class="sep" />
        <div class="sublabel head tiprow">${l.t("expire")}${helpTip(l, "help_expire")}</div>
        ${
          this._trigger
            ? html`<label class="field"
                >${l.t("expire_hours_n")}
                <input
                  type="number"
                  min="1"
                  .value=${/^\+(\d+)h$/.exec(expire)?.[1] ?? "12"}
                  @change=${(e: Event) =>
                    this._update({
                      expire: `+${Math.max(1, Math.round(Number((e.target as HTMLInputElement).value)) || 12)}h`,
                    })}
                />
              </label>`
            : html`<div class="segmented">
                <button
                  aria-pressed=${kind === "end"}
                  @click=${() => this._update({ expire: "event_end" })}
                >
                  ${l.t("expire_event_end")}
                </button>
                <button
                  aria-pressed=${kind === "day"}
                  @click=${() => kind !== "day" && this._update({ expire: "event_day 12:00" })}
                >
                  ${l.t("expire_event_day")}
                </button>
                <button
                  aria-pressed=${kind === "custom"}
                  @click=${() => kind !== "custom" && this._update({ expire: "+1d 12:00" })}
                >
                  ${l.t("expire_custom")}
                </button>
              </div>`
        }
        ${
          this._trigger
            ? nothing
            : kind === "day"
              ? html`<input
                  type="time"
                  .value=${dayMatch![1].padStart(5, "0")}
                  @change=${(e: Event) =>
                    this._update({ expire: `event_day ${(e.target as HTMLInputElement).value}` })}
                />`
              : kind === "custom"
                ? html`<input
                    .value=${expire}
                    @change=${(e: Event) => this._update({ expire: (e.target as HTMLInputElement).value })}
                  />`
                : nothing
        }
      `,
    );
  }

  private _setSubstituteWhen(changes: { entity_id?: string; state?: string }): void {
    const assignee = this._rule.assignee;
    if (!assignee) return;
    const when = { entity_id: "", state: "", ...assignee.substitute_when, ...changes };
    const next = { ...assignee };
    if (when.entity_id || when.state) next.substitute_when = when;
    else delete next.substitute_when;
    this._update({ assignee: next });
  }

  /** Person chips; `single` picks at most one. */
  private _personChips(
    selected: string[],
    single: boolean,
    onChange: (ids: string[]) => void,
  ): TemplateResult {
    if (!this._persons.length) {
      return html`<div class="hint">${this._l.t("no_companion_persons")}</div>`;
    }
    return html`<div class="wrap">
      ${this._persons.map((p) => {
        const on = selected.includes(p.entity_id);
        return html`<button
          class="chip ${on ? "accent" : ""}"
          aria-pressed=${on}
          @click=${() =>
            onChange(
              on
                ? selected.filter((id) => id !== p.entity_id)
                : single
                  ? [p.entity_id]
                  : [...selected, p.entity_id],
            )}
        >
          ${p.name}
        </button>`;
      })}
    </div>`;
  }

  /** Known states of an entity: the current one plus the usual ones of its domain. */
  private _stateOptions(entityId: string): string[] {
    const domain = entityId.split(".")[0];
    const usual =
      domain === "person" || domain === "device_tracker"
        ? ["home", "not_home"]
        : ["on", "off"].filter(() => !["sensor", "select", "input_select"].includes(domain));
    const now = this.hass?.states[entityId]?.state;
    return [...new Set([...(now ? [now] : []), ...usual])];
  }

  private _stepAdvanced(): TemplateResult {
    const l = this._l;
    const r = this._rule;
    const assignee = r.assignee;
    const activation = r.activation;
    const stages = r.escalation ?? [];
    const stats = Object.entries(this.rule.status?.assignee_stats ?? {});
    const setActivation = (changes: Partial<NonNullable<Rule["activation"]>> | null) => {
      if (changes === null) {
        this._update({ activation: null }, true);
        return;
      }
      const next = { conditions: [], match: "all" as const, ...activation, ...changes };
      if (!next.season) delete next.season;
      this._update({ activation: next }, true);
    };
    return this._step(
      7,
      "step_advanced",
      html`
        <div class="sublabel head tiprow">${l.t("assignee")}${helpTip(l, "assignee_hint")}</div>
        ${this._personChips(assignee?.persons ?? [], false, (persons) =>
          this._update({
            assignee: persons.length
              ? { ...assignee, persons, rotation: assignee?.rotation ?? "fixed" }
              : null,
          }),
        )}
        ${
          assignee
            ? html`<label class="field"
                  >${l.t("rotation")}
                  <select
                    @change=${(e: Event) =>
                      this._update({
                        assignee: {
                          ...assignee,
                          rotation: (e.target as HTMLSelectElement).value as Rotation,
                        },
                      })}
                  >
                    ${(["fixed", "weekly", "per_event", "after_last"] as const).map(
                      (rot) =>
                        html`<option
                          value=${rot}
                          ?selected=${(assignee.rotation ?? "fixed") === rot}
                        >
                          ${l.t(`rotation_${rot}` as StringKey)}
                        </option>`,
                    )}
                  </select>
                </label>

                <div class="sublabel tiprow">
                  ${l.t("substitute")}${helpTip(l, "help_substitute")}
                </div>
                ${this._personChips(
                  assignee.substitute ? [assignee.substitute] : [],
                  true,
                  (ids) => {
                    const next = { ...assignee };
                    if (ids[0]) next.substitute = ids[0];
                    else delete next.substitute;
                    this._update({ assignee: next });
                  },
                )}
                <div class="sublabel">${l.t("substitute_when")}</div>
                <div class="row">
                  <laeutwerk-field
                    class="grow"
                    .hass=${this.hass}
                    .localize=${l}
                    .selector=${{ entity: {} }}
                    .value=${assignee.substitute_when?.entity_id ?? ""}
                    @value-changed=${(e: CustomEvent<{ value: string }>) =>
                      this._setSubstituteWhen({ entity_id: e.detail.value || "" })}
                  ></laeutwerk-field>
                  <label class="field grow"
                    >${l.t("substitute_state")}
                    <input
                      list="lw-states"
                      .value=${assignee.substitute_when?.state ?? ""}
                      @change=${(e: Event) =>
                        this._setSubstituteWhen({ state: (e.target as HTMLInputElement).value })}
                    />
                    <datalist id="lw-states">
                      ${this._stateOptions(assignee.substitute_when?.entity_id ?? "").map(
                        (st) => html`<option value=${st}></option>`,
                      )}
                    </datalist>
                  </label>
                </div>
                ${
                  stats.length
                    ? html`<div class="wrap">
                        <span class="hint">${l.t("stats")}:</span>
                        ${stats.map(([who, n]) => html`<span class="chip">${who} · ${n}×</span>`)}
                      </div>`
                    : nothing
                }`
            : nothing
        }
        <hr class="sep" />
        <div class="row">
          <div class="sublabel head grow">${l.t("activation")}</div>
          ${
            activation
              ? html`<div class="segmented small">
                  ${(["all", "any"] as const).map(
                    (m) =>
                      html`<button
                        aria-pressed=${(activation.match ?? "all") === m}
                        @click=${() => setActivation({ match: m })}
                      >
                        ${l.t(m === "all" ? "match_all" : "match_any")}
                      </button>`,
                  )}
                </div>`
              : nothing
          }
        </div>
        <laeutwerk-field
          .hass=${this.hass}
          .localize=${l}
          .selector=${{ condition: {} }}
          .value=${activation?.conditions ?? EMPTY}
          @value-changed=${(e: CustomEvent<{ value: HaConfig[] | undefined }>) => {
            const conditions = e.detail.value ?? [];
            if (!conditions.length && !activation?.season) setActivation(null);
            else setActivation({ conditions });
          }}
        ></laeutwerk-field>
        <hr class="sep" />
        <div class="sublabel head">${l.t("season")}</div>
        <div class="row season">
          ${this._monthDay(activation?.season?.from ?? "", l.t("season_from"), (from) => {
            const to = activation?.season?.to ?? "";
            if (!from && !to && !activation?.conditions.length) setActivation(null);
            else setActivation({ season: from || to ? { from, to } : undefined });
          })}
          <span>–</span>
          ${this._monthDay(activation?.season?.to ?? "", l.t("season_to"), (to) => {
            const from = activation?.season?.from ?? "";
            if (!from && !to && !activation?.conditions.length) setActivation(null);
            else setActivation({ season: from || to ? { from, to } : undefined });
          })}
        </div>
        <hr class="sep" />
        <div class="sublabel head tiprow">${l.t("escalation")}${helpTip(l, "escalation_hint")}</div>
        <div class="divided">
          ${stages.map(
            (stage, i) =>
              html`<div class="stage-item">
                <div class="row stage-row">
                  <span class="chip stagechip-big" style="--stage: ${stageColor(r, i + 1)}"
                    >${l.t("stage_n", { n: i + 1 })}</span
                  >
                  ${this._stageInput(stage.after, (after) =>
                    this._update({
                      escalation: stages.map((x, j) => (j === i ? { ...x, after } : x)),
                    }),
                  )}
                  <button
                    class="mini"
                    aria-label=${l.t("remove")}
                    ?disabled=${i !== stages.length - 1}
                    @click=${() =>
                      this._update({
                        escalation: stages.slice(0, -1),
                        signals: r.signals.map((sig) =>
                          (sig.stage ?? 0) > stages.length - 1
                            ? { ...sig, stage: stages.length - 1 }
                            : sig,
                        ),
                      })}
                  >
                    <ha-icon icon="mdi:close"></ha-icon>
                  </button>
                </div>
                <laeutwerk-field
                  .hass=${this.hass}
                  .localize=${l}
                  .label=${`${l.t("stage_n", { n: i + 1 })} · ${l.t("stage_color")}`}
                  .selector=${{ color_rgb: {} }}
                  .swatches=${this._kwSwatches()}
                  .value=${stageColor(r, i + 1) ?? ""}
                  @value-changed=${(e: CustomEvent<{ value: string }>) =>
                    this._update({
                      escalation: stages.map((x, j) =>
                        j === i ? { ...x, color: e.detail.value || undefined } : x,
                      ),
                    })}
                ></laeutwerk-field>
              </div>`,
          )}
        </div>
        <div class="wrap">
          <button
            class="chip dashed"
            @click=${() =>
              this._update({ escalation: [...stages, { after: stages.length ? "21:30" : "2h" }] })}
          >
            <ha-icon icon="mdi:plus"></ha-icon>${l.t("add_stage")}
          </button>
        </div>
        <hr class="sep" />
        <div class="sublabel head tiprow">${l.t("on_done")}${helpTip(l, "on_done_hint")}</div>
        ${this._toggle(l.t("confirm_send"), !!r.confirm, (v) =>
          this._update({
            confirm: v ? { message: l.t("confirm_default"), clear_after: 10 } : null,
          }),
        )}
        ${
          r.confirm
            ? html`<laeutwerk-suggest
                  .label=${l.t("confirm_message")}
                  .value=${r.confirm.message}
                  .variables=${availableVariables(r)}
                  @value-changed=${(e: CustomEvent<{ value: string }>) =>
                    this._update({ confirm: { ...r.confirm!, message: e.detail.value } })}
                ></laeutwerk-suggest>
                <label class="field"
                  >${l.t("confirm_clear")}
                  <input
                    type="number"
                    min="0"
                    .value=${String(r.confirm.clear_after)}
                    @change=${(e: Event) =>
                      this._update({
                        confirm: {
                          ...r.confirm!,
                          clear_after: Math.max(
                            0,
                            Number((e.target as HTMLInputElement).value) || 0,
                          ),
                        },
                      })}
                  />
                </label>`
            : nothing
        }
        <laeutwerk-field
          .hass=${this.hass}
          .localize=${l}
          .selector=${{ action: {} }}
          .value=${r.on_done ?? EMPTY}
          @value-changed=${(e: CustomEvent<{ value: HaConfig[] | undefined }>) =>
            this._update({ on_done: e.detail.value ?? [] })}
        ></laeutwerk-field>
      `,
    );
  }

  /** Day and month pickers for a season border ("MM-DD"). */
  private _monthDay(
    value: string,
    label: string,
    onChange: (value: string) => void,
  ): TemplateResult {
    const l = this._l;
    const [month, day] = value ? value.split("-").map(Number) : [0, 0];
    const emit = (m: number, d: number) =>
      onChange(m && d ? `${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}` : "");
    return html`<span class="monthday" role="group" aria-label=${label}>
      <select
        aria-label=${`${label} ${l.t("season_day")}`}
        @change=${(e: Event) => emit(month || 1, Number((e.target as HTMLSelectElement).value))}
      >
        <option value="0" ?selected=${!day}>–</option>
        ${Array.from({ length: 31 }, (_, n) => n + 1).map(
          (d) => html`<option value=${d} ?selected=${d === day}>${d}.</option>`,
        )}
      </select>
      <select
        aria-label=${`${label} ${l.t("season_month")}`}
        @change=${(e: Event) => emit(Number((e.target as HTMLSelectElement).value), day || 1)}
      >
        <option value="0" ?selected=${!month}>–</option>
        ${Array.from({ length: 12 }, (_, n) => n + 1).map(
          (m) => html`<option value=${m} ?selected=${m === month}>${l.monthShort(m - 1)}</option>`,
        )}
      </select>
    </span>`;
  }

  /** Escalation stage: after a number of minutes / hours, or at a time of day. */
  private _stageInput(after: string, onChange: (after: string) => void): TemplateResult {
    const l = this._l;
    const atTime = /^\d{1,2}:\d{2}$/.test(after);
    const match = /^(\d+)\s*([mh]?)$/.exec(after);
    const amount = match ? Number(match[1]) : 2;
    const unit = match?.[2] === "m" ? "m" : "h";
    return html`<div class="stage grow">
      <div class="segmented small">
        <button aria-pressed=${!atTime} @click=${() => atTime && onChange("2h")}>
          ${l.t("stage_after_mode")}
        </button>
        <button aria-pressed=${atTime} @click=${() => !atTime && onChange("21:30")}>
          ${l.t("stage_at_mode")}
        </button>
      </div>
      ${
        atTime
          ? html`<input
              type="time"
              .value=${after.padStart(5, "0")}
              @change=${(e: Event) => onChange((e.target as HTMLInputElement).value)}
            />`
          : html`<div class="row">
              <input
                type="number"
                min="1"
                .value=${String(amount)}
                @change=${(e: Event) =>
                  onChange(`${Math.max(1, Number((e.target as HTMLInputElement).value))}${unit}`)}
              />
              <select
                @change=${(e: Event) =>
                  onChange(`${amount}${(e.target as HTMLSelectElement).value}`)}
              >
                <option value="m" ?selected=${unit === "m"}>${l.t("minutes_short")}</option>
                <option value="h" ?selected=${unit === "h"}>${l.t("hours_short")}</option>
              </select>
            </div>`
      }
    </div>`;
  }

  private _toggle(
    label: string,
    value: boolean,
    onChange: (v: boolean) => void,
    help?: StringKey,
  ): TemplateResult {
    return html`<div class="toggle">
      <span class="tiprow">${label}${help ? helpTip(this._l, help) : nothing}</span>
      <button
        class="switch"
        role="switch"
        aria-checked=${value}
        aria-label=${label}
        @click=${() => onChange(!value)}
      >
        <span></span>
      </button>
    </div>`;
  }

  static styles = [
    tokens,
    shared,
    css`
      .page {
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      .sublabel {
        font-size: 12px;
        font-weight: 600;
        color: var(--lw-text-2);
        margin-top: 4px;
      }
      .color input {
        width: 56px;
        padding: 4px;
      }
      /* Keyword table: horizontally scrollable, fixed column widths, sticky first column. */
      .kwwrap {
        position: relative;
      }
      .kwwrap::after {
        content: "";
        position: absolute;
        top: 0;
        right: 0;
        bottom: 6px;
        width: 28px;
        pointer-events: none;
        opacity: 0;
        transition: opacity 0.15s;
        background: linear-gradient(to right, transparent, var(--lw-bg));
        border-radius: 0 12px 12px 0;
      }
      .kwwrap.more::after {
        opacity: 0.9;
      }
      .kwtable {
        overflow-x: auto;
        padding-bottom: 6px;
        overscroll-behavior-x: contain;
        margin: 0 -4px;
      }
      .kwinner {
        display: flex;
        flex-direction: column;
        width: max-content;
        min-width: 100%;
      }
      .kwrow {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 6px 8px 6px 0;
        border-top: 1px solid var(--lw-border);
      }
      .kwrow.head {
        border-top: 0;
        align-items: flex-end;
        padding: 0 8px 2px 0;
      }
      .hcell {
        font-size: 12px;
        font-weight: 600;
        color: var(--lw-text-2);
      }
      .stick {
        position: sticky;
        left: 0;
        z-index: 1;
        width: 176px;
        flex-shrink: 0;
        box-sizing: border-box;
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 2px 8px 2px 6px;
        border-right: 1px solid var(--lw-border);
        /* Solid copy of the panel colour, so scrolled cells do not show through. */
        background: linear-gradient(var(--lw-surface), var(--lw-surface)), var(--lw-bg);
        box-shadow: 6px 0 6px -6px rgba(0, 0, 0, 0.35);
      }
      .hcell.stick {
        padding-top: 0;
        padding-bottom: 0;
        box-shadow: none;
        align-items: center;
        gap: 0;
      }
      .lookbtn {
        position: relative;
        width: 44px;
        height: 44px;
        flex-shrink: 0;
        display: inline-flex;
        align-items: center;
        justify-content: center;
      }
      .plusdot {
        position: absolute;
        right: 1px;
        bottom: 1px;
        width: 16px;
        height: 16px;
        border-radius: 8px;
        background: var(--lw-accent);
        color: var(--lw-on-accent);
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .plusdot ha-icon {
        --mdc-icon-size: 12px;
      }
      .kwbadge {
        border-radius: 50%;
        flex-shrink: 0;
        display: inline-flex;
        align-items: center;
        justify-content: center;
      }
      .kwbadge ha-icon {
        --mdc-icon-size: 55%;
      }
      .hitbadges {
        display: inline-flex;
        gap: 4px;
        flex-shrink: 0;
      }
      .hitbadges .kwbadge ha-icon {
        --mdc-icon-size: 16px;
      }
      .stick .kwbadge ha-icon {
        --mdc-icon-size: 20px;
      }
      .kwinput {
        flex: 1;
        min-width: 0;
      }
      .c-mode {
        width: 104px;
        flex-shrink: 0;
      }
      .c-var {
        width: 148px;
        flex-shrink: 0;
      }
      .c-mode select {
        padding: 0 6px;
        font-size: 13px;
      }
      .tiprow {
        display: flex;
        align-items: center;
        gap: 4px;
      }
      .vhead {
        display: flex;
        align-items: center;
        gap: 2px;
      }
      .vhead .x {
        width: 28px;
      }
      .vname {
        min-height: 36px;
        padding: 0 8px;
        font-size: 13px;
        font-family: ui-monospace, monospace;
        background: var(--lw-surface-2);
        color: var(--lw-text);
      }
      .plural {
        position: relative;
        width: 26px;
        height: 26px;
        flex-shrink: 0;
        border-radius: 13px;
        border: 1px dashed var(--lw-border);
        font-size: 12px;
        font-weight: 600;
        font-family: ui-monospace, monospace;
        color: var(--lw-text-2);
      }
      .plural::before {
        content: "";
        position: absolute;
        inset: -9px -3px;
      }
      .plural[aria-checked="true"] {
        border-style: solid;
        background: color-mix(in srgb, var(--lw-accent) 14%, transparent);
        color: var(--lw-text);
      }
      .addbtn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        min-height: 44px;
        padding: 0 16px;
        border-radius: 22px;
        border: 1px dashed var(--lw-border);
        font-size: 13px;
        font-weight: 600;
        color: var(--lw-text);
      }
      .addbtn ha-icon {
        --mdc-icon-size: 18px;
      }
      .addbtn.accent {
        border-style: solid;
        background: color-mix(in srgb, var(--lw-accent) 16%, transparent);
      }
      .x {
        width: 36px;
        height: 36px;
        flex-shrink: 0;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        color: var(--lw-text-2);
      }
      .x ha-icon {
        --mdc-icon-size: 18px;
      }
      .x.small {
        width: 28px;
        height: 28px;
        margin-right: -8px;
      }
      .preview .muted,
      .muted {
        color: var(--lw-text-2);
        font-size: 12px;
      }
      .preview {
        display: flex;
        gap: 8px;
        align-items: flex-start;
        font-size: 13px;
        padding: 10px 12px;
        border-radius: 12px;
        background: var(--lw-surface-2);
      }
      .preview ha-icon {
        --mdc-icon-size: 16px;
        color: var(--lw-text-2);
      }
      .prev {
        display: flex;
        align-items: center;
        gap: 8px;
        min-height: 36px;
        font-size: 13px;
      }
      .prev .date {
        width: 52px;
        color: var(--lw-text-2);
        flex-shrink: 0;
      }
      .dot {
        width: 10px;
        height: 10px;
        border-radius: 5px;
        flex-shrink: 0;
        box-shadow: 0 0 0 1px var(--lw-border);
      }
      .addtime {
        flex-wrap: wrap;
      }
      .addtime select {
        flex: 1 1 100%;
      }
      .sig {
        display: flex;
        align-items: center;
        gap: 10px;
      }
      .sigmain {
        flex: 1;
        min-width: 0;
        display: flex;
        align-items: center;
        gap: 10px;
        text-align: left;
        min-height: 52px;
      }
      .sigmain .grow {
        display: flex;
        flex-direction: column;
        gap: 2px;
      }
      .ackrow {
        display: flex;
        align-items: center;
        gap: 10px;
        min-height: 44px;
        font-size: 14px;
      }
      .extra {
        flex-wrap: wrap;
      }
      .sig {
        border-left: 3px solid var(--stage, transparent);
        padding-left: 6px;
      }
      .icon.staged {
        background: color-mix(in srgb, var(--stage) 25%, transparent);
        color: var(--stage);
      }
      .stagechip {
        display: inline-block;
        padding: 0 6px;
        margin-right: 4px;
        border-radius: 8px;
        font-size: 11px;
        font-weight: 600;
        background: color-mix(in srgb, var(--stage) 22%, transparent);
        color: var(--lw-text);
      }
      .kcolor {
        width: 100px;
        flex-shrink: 0;
      }
      .colorfield {
        width: 120px;
        flex-shrink: 0;
      }
      .stage-item {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .stagechip-big {
        background: color-mix(in srgb, var(--stage) 30%, transparent);
        border: 2px solid var(--stage);
        min-height: 32px;
        flex-shrink: 0;
      }
      .stagecolor {
        position: relative;
        display: inline-flex;
        flex-shrink: 0;
        cursor: pointer;
      }
      .stagecolor .chip {
        background: color-mix(in srgb, var(--stage) 30%, transparent);
        border: 2px solid var(--stage);
        min-height: 32px;
      }
      .stagecolor input[type="color"] {
        position: absolute;
        inset: 0;
        opacity: 0;
        width: 100%;
        height: 100%;
        cursor: pointer;
      }
      .monthday {
        display: inline-flex;
        gap: 4px;
        flex: 1;
      }
      .monthday select {
        padding: 0 6px;
      }
      .season {
        align-items: center;
      }
      .stage {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .stage select {
        width: auto;
      }
      .step.head {
        width: 100%;
        text-align: left;
        min-height: 44px;
      }
      .step.head .text {
        display: flex;
        flex-direction: column;
        gap: 2px;
        min-width: 0;
      }
      .summary {
        font-size: 12px;
        font-weight: 400;
        color: var(--lw-text-2);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .badge {
        min-width: 20px;
        height: 20px;
        border-radius: 10px;
        background: var(--lw-danger);
        color: #fff;
        font-size: 12px;
        font-weight: 700;
        display: inline-flex;
        align-items: center;
        justify-content: center;
      }
      .panel.has-error {
        border-color: color-mix(in srgb, var(--lw-danger) 60%, transparent);
      }
      .pill.next {
        align-self: flex-end;
        min-height: 40px;
      }
      .error details {
        margin-top: 4px;
        font-size: 12px;
      }
      .error code {
        white-space: pre-wrap;
        word-break: break-word;
      }
      .yaml {
        min-height: 180px;
        font-family: ui-monospace, monospace;
        font-size: 12px;
      }
      .segmented.small button {
        min-height: 32px;
        padding: 0 12px;
      }
      .vars .chip {
        min-height: 32px;
        font-family: ui-monospace, monospace;
      }
      .ackrow .grow {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .ackblock {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
    `,
  ];
}
