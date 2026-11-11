/**
 * Rule editor (DESIGN C1.2): six steps in cards – calendar, keyword table
 * (horizontally scrollable) with live preview, reminder times and repeat,
 * signals, acknowledgement, details. Opens the signal editor as a sub page.
 */
import { LitElement, css, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import {
  SIGNAL_ICONS,
  defaultSignal,
  describeTimespec,
  formatDate,
  relativeDayTime,
  renameColumn,
  signalSummary,
} from "./format";
import type { Localizer, StringKey } from "./localize";
import { shared, tokens } from "./styles";
import type {
  Acknowledge,
  HaConfig,
  HomeAssistant,
  KeywordRow,
  MatchMode,
  PreviewResult,
  Rule,
  Signal,
} from "./types";

type TimeKind = "days" | "same" | "hours" | "minutes" | "custom";

function errorText(err: unknown): string {
  if (err && typeof err === "object" && "message" in err) return String(err.message);
  return String(err);
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
  private _previewTimer?: number;

  protected willUpdate(changed: PropertyValues): void {
    if (changed.has("rule") && this.rule) {
      const copy = clone(this.rule);
      delete copy.status;
      this._rule = copy;
      this._schedulePreview(0);
    }
  }

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    window.clearTimeout(this._previewTimer);
  }

  private get _l(): Localizer {
    return this.localize;
  }

  private _update(changes: Partial<Rule>, preview = false): void {
    this._rule = { ...this._rule, ...changes };
    if (preview) this._schedulePreview(500);
  }

  private _schedulePreview(delay: number): void {
    window.clearTimeout(this._previewTimer);
    this._previewTimer = window.setTimeout(() => void this._loadPreview(), delay);
  }

  private async _loadPreview(): Promise<void> {
    if (!this.hass || !this._rule?.sources.length) {
      this._preview = undefined;
      return;
    }
    const rule = clone(this._rule);
    rule.filter.keywords.rows = rule.filter.keywords.rows.filter((r) => r.match.trim());
    // Columns may still be half-typed: the preview needs no variables of signals.
    rule.signals = [];
    try {
      this._preview = await this.hass.callWS<PreviewResult>({
        type: "laeutwerk/preview",
        rule: { ...rule, reminders: rule.reminders.length ? rule.reminders : [{ at: "09:00" }] },
        limit: 5,
      });
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
    this._saving = true;
    this._error = undefined;
    const rule = clone(this._rule);
    rule.filter.keywords.rows = rule.filter.keywords.rows.filter((r) => r.match.trim());
    try {
      const saved = rule.id
        ? await this.hass.callWS<Rule>({ type: "laeutwerk/rules/update", rule_id: rule.id, rule })
        : await this.hass.callWS<Rule>({ type: "laeutwerk/rules/create", rule });
      this._emit("saved", saved);
    } catch (err) {
      this._error = this._l.t("failed", { error: errorText(err) });
    } finally {
      this._saving = false;
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

  private _addColumn(): void {
    const { columns, rows } = this._rule.filter.keywords;
    let name = "spalte";
    for (let n = 2; columns.includes(name); n++) name = `spalte${n}`;
    const keywords = {
      columns: [...columns, name],
      rows: rows.map((r) => ({ ...r, [name]: "" })),
    };
    this._update({ filter: { ...this._rule.filter, keywords } });
  }

  private _removeColumn(index: number): void {
    const { columns, rows } = this._rule.filter.keywords;
    const name = columns[index];
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
        @apply=${this._applySignal}
        @cancel=${() => (this._signal = undefined)}
        @delete=${this._deleteSignal}
      ></laeutwerk-signal-editor>`;
    }
    const l = this._l;
    const valid =
      this._rule.name.trim() && this._rule.sources.length && this._rule.reminders.length;
    return html`<div class="page">
      <div class="separator">
        ${this._rule.id ? l.t("edit_rule") : l.t("new_rule")}<span class="line"></span>
      </div>
      ${this._stepCalendar()} ${this._stepEvents()} ${this._stepWhen()} ${this._stepSignals()}
      ${this._stepAck()} ${this._stepDetails()}
      ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
      ${
        this._rule.id
          ? html`<button class="pill danger wide" @click=${this._delete}>
              ${this._confirmDelete ? l.t("confirm_delete") : l.t("delete_rule")}
            </button>`
          : nothing
      }
      <div class="actions">
        <button class="pill outline" @click=${() => this._emit("cancel")}>${l.t("cancel")}</button>
        <button class="pill primary" ?disabled=${!valid || this._saving} @click=${this._save}>
          ${l.t("save")}
        </button>
      </div>
    </div>`;
  }

  private _step(num: number, title: StringKey, body: TemplateResult): TemplateResult {
    return html`<section class="panel">
      <div class="step"><span class="num">${num}</span>${this._l.t(title)}</div>
      ${body}
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
          <label class="field color"
            >${l.t("color")}
            <input
              type="color"
              .value=${r.color ?? "#8a8a94"}
              @change=${(e: Event) => this._update({ color: (e.target as HTMLInputElement).value })}
            />
          </label>
        </div>
        <laeutwerk-field
          .hass=${this.hass}
          .localize=${l}
          .label=${l.t("calendars")}
          .selector=${{ entity: { domain: "calendar", multiple: true } }}
          .value=${r.sources}
          @value-changed=${(e: CustomEvent<{ value: string[] | string }>) => {
            const value = e.detail.value;
            this._update({ sources: Array.isArray(value) ? value : value ? [value] : [] }, true);
          }}
        ></laeutwerk-field>
      `,
    );
  }

  private _stepEvents(): TemplateResult {
    const l = this._l;
    const { columns, rows } = this._rule.filter.keywords;
    const example = columns[0] ?? "tonne";
    return this._step(
      2,
      "step_events",
      html`
        ${this._toggle(l.t("only_all_day"), this._rule.filter.all_day, (v) =>
          this._update({ filter: { ...this._rule.filter, all_day: v } }, true),
        )}
        <div class="table" role="table">
          <div class="tr head" role="row">
            <div class="th kw" role="columnheader">${l.t("keyword")}</div>
            ${columns.map(
              (c, i) =>
                html`<div class="th col" role="columnheader">
                  <input
                    class="colname"
                    .value=${c}
                    aria-label=${l.t("add_column")}
                    @change=${(e: Event) =>
                      this._update(
                        renameColumn(this._rule, i, (e.target as HTMLInputElement).value),
                        true,
                      )}
                  />
                  <button
                    class="x"
                    aria-label=${l.t("remove")}
                    @click=${() => this._removeColumn(i)}
                  >
                    <ha-icon icon="mdi:close"></ha-icon>
                  </button>
                </div>`,
            )}
            <div class="th end"></div>
          </div>
          ${rows.map(
            (row, i) =>
              html`<div class="tr" role="row">
                <div class="td kw" role="cell">
                  <input
                    .value=${row.match}
                    @input=${(e: Event) => this._setRow(i, { match: (e.target as HTMLInputElement).value })}
                  />
                  <select
                    aria-label="mode"
                    @change=${(e: Event) =>
                      this._setRow(i, { mode: (e.target as HTMLSelectElement).value as MatchMode })}
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
                    html`<div class="td col" role="cell">
                      <input
                        .value=${row[c] ?? ""}
                        @input=${(e: Event) => this._setRow(i, { [c]: (e.target as HTMLInputElement).value })}
                      />
                    </div>`,
                )}
                <div class="td end" role="cell">
                  <button
                    class="x"
                    aria-label=${l.t("remove")}
                    @click=${() => this._setRows(rows.filter((_, j) => j !== i))}
                  >
                    <ha-icon icon="mdi:close"></ha-icon>
                  </button>
                </div>
              </div>`,
          )}
        </div>
        <div class="wrap">
          <button
            class="chip dashed"
            @click=${() =>
              this._setRows([
                ...rows,
                { match: "", ...Object.fromEntries(columns.map((c) => [c, ""])) },
              ])}
          >
            <ha-icon icon="mdi:plus"></ha-icon>${l.t("add_keyword")}
          </button>
          <button class="chip dashed" @click=${this._addColumn}>
            <ha-icon icon="mdi:plus"></ha-icon>${l.t("add_column")}
          </button>
        </div>
        <div class="hint">
          ${
            rows.length
              ? l.t("plural_hint", { example: `{${example}}`, plural: `{${example}n}` })
              : l.t("no_keywords")
          }
        </div>
        ${this._previewList()}
      `,
    );
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
          ? html`<div class="list">
              ${preview.events.map(
                (e) =>
                  html`<div class="prev">
                    <span class="date">${formatDate(e.start, l, tz)}</span>
                    <span class="grow">${e.titles.join(" + ")}</span>
                    ${e.colors.map((c) => html`<span class="dot" style="background:${c}"></span>`)}
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
    const repeat =
      r.repeat === "none" ? "none" : Number(r.repeat.every) === 60 ? "hourly" : "custom";
    const first = this._preview?.events[0]?.reminder_times?.[0];
    const now = new Date();
    return this._step(
      3,
      "step_when",
      html`
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
        <div class="sublabel">${l.t("repeat")}</div>
        <div class="segmented">
          <button
            aria-pressed=${repeat === "none"}
            @click=${() => this._update({ repeat: "none" })}
          >
            ${l.t("repeat_once")}
          </button>
          <button
            aria-pressed=${repeat === "hourly"}
            @click=${() => this._update({ repeat: { every: 60, max: 24 } })}
          >
            ${l.t("repeat_hourly")}
          </button>
          <button
            aria-pressed=${repeat === "custom"}
            @click=${() => repeat !== "custom" && this._update({ repeat: { every: 30, max: 10 } })}
          >
            ${l.t("repeat_custom")}
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
        ${signals.length ? nothing : html`<div class="hint">${l.t("no_signals")}</div>`}
        <div class="list">
          ${signals.map(
            (s, i) =>
              html`<div class="sig">
                <button class="sigmain" @click=${() => this._openSignal(i)}>
                  <span class="icon small"><ha-icon .icon=${SIGNAL_ICONS[s.type]}></ha-icon></span>
                  <span class="grow">
                    <span class="name">${l.t(`type_${s.type}` as StringKey)}</span>
                    <span class="sub">${signalSummary(s, l)}</span>
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
              </div>`,
          )}
        </div>
        <div class="wrap">
          ${(["notify", "light_signal", "announce", "action"] as const).map(
            (type) =>
              html`<button
                class="chip dashed"
                @click=${() => this._openSignal(signals.length, defaultSignal(type, this._rule))}
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
                <input
                  .value=${a.tag_id ?? ""}
                  placeholder=${l.t("ack_tag_placeholder")}
                  @input=${(e: Event) => setAt(i, { tag_id: (e.target as HTMLInputElement).value })}
                />
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
        <label class="field"
          >${l.t("ack_label")}
          <input
            .value=${this._rule.ack_label ?? ""}
            placeholder=${l.t("ack_label_placeholder")}
            @input=${(e: Event) =>
              this._update({ ack_label: (e.target as HTMLInputElement).value || null })}
          />
        </label>
        <div class="hint">${l.t("ack_always")}</div>
      `,
    );
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
        ${this._toggle(l.t("bundle"), r.bundle, (v) => this._update({ bundle: v }, true))}
        <div class="hint">${l.t("bundle_hint")}</div>
        <div class="sublabel">${l.t("expire")}</div>
        <div class="segmented">
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
        </div>
        ${
          kind === "day"
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

  private _toggle(label: string, value: boolean, onChange: (v: boolean) => void): TemplateResult {
    return html`<div class="toggle">
      <span>${label}</span>
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
      /* Keyword table: horizontally scrollable with fixed column widths. */
      .table {
        overflow-x: auto;
        display: flex;
        flex-direction: column;
        gap: 6px;
        padding-bottom: 4px;
        overscroll-behavior-x: contain;
      }
      .tr {
        display: flex;
        gap: 6px;
        width: max-content;
        align-items: center;
      }
      .th {
        font-size: 12px;
        font-weight: 600;
        color: var(--lw-text-2);
      }
      .kw {
        width: 168px;
        flex-shrink: 0;
        display: flex;
        gap: 4px;
      }
      .td.kw input {
        width: 92px;
      }
      .td.kw select {
        width: 72px;
        padding: 0 4px;
        font-size: 12px;
      }
      .col {
        width: 120px;
        flex-shrink: 0;
        display: flex;
        align-items: center;
        gap: 2px;
      }
      .end {
        width: 36px;
        flex-shrink: 0;
      }
      .colname {
        min-height: 36px;
        font-size: 12px;
        font-family: ui-monospace, monospace;
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
        --mdc-icon-size: 16px;
      }
      .x.small {
        width: 28px;
        height: 28px;
        margin-right: -8px;
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
      .ackblock {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
    `,
  ];
}
