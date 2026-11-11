/**
 * laeutwerk-card: "Heute & demnächst" overview, single rule view, compact
 * line and the rule editor (DESIGN.md C1).
 */
import { LitElement, css, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import {
  buildOverview,
  emptyRule,
  finishedLine,
  formatDate,
  openStatus,
  relativeDay,
  relativeDayTime,
  reminderTitle,
} from "./format";
import { LaeutwerkCardEditor } from "./card-editor";
import { LaeutwerkField } from "./ha-field";
import { localizer, type Localizer } from "./localize";
import { defineElements } from "./register";
import { applyRuleEvent } from "./rule-events";
import { LaeutwerkRuleEditor } from "./rule-editor";
import { LaeutwerkSignalEditor } from "./signal-editor";
import { shared, tokens } from "./styles";
import type {
  HistoryEntry,
  HomeAssistant,
  LaeutwerkCardConfig,
  Reminder,
  Rule,
  RuleEvent,
} from "./types";
import { CARD_VERSION } from "./version";

const DEFAULT_ICON = "mdi:bell-ring-outline";

function errorMessage(err: unknown): string {
  if (err && typeof err === "object" && "message" in err) return String(err.message);
  return String(err);
}

export class LaeutwerkCard extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @state() private _config?: LaeutwerkCardConfig;
  @state() private _rules?: Rule[];
  @state() private _error?: string;
  @state() private _busy?: string;
  @state() private _actionError?: string;
  /** Rule open in the editor (new rule: without id). */
  @state() private _editing?: Rule;
  @state() private _now = new Date();
  /** History of the rule shown with view: rule. */
  @state() private _history?: HistoryEntry[];
  private _historyKey?: string;
  private _unsub?: Promise<() => Promise<void> | void>;
  private _clock?: number;

  // --- Lovelace API ---------------------------------------------------------

  public setConfig(config: LaeutwerkCardConfig): void {
    if (!config || typeof config !== "object") throw new Error("Invalid configuration");
    if (config.view && !["overview", "rule"].includes(config.view)) {
      throw new Error("view must be overview or rule");
    }
    this._config = { view: "overview", show_upcoming: true, show_done: true, ...config };
  }

  public getCardSize(): number {
    if (this._config?.compact) return 1;
    return 3 + (this._rules?.length ?? 0);
  }

  public getGridOptions() {
    if (this._config?.compact) return { columns: 12, min_columns: 6, rows: 1, min_rows: 1 };
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  public static getConfigElement(): HTMLElement {
    return document.createElement("laeutwerk-card-editor");
  }

  public static async getStubConfig(hass?: HomeAssistant): Promise<Partial<LaeutwerkCardConfig>> {
    void hass;
    return { view: "overview" };
  }

  // --- Lifecycle ------------------------------------------------------------

  public connectedCallback(): void {
    super.connectedCallback();
    this._startClock();
    if (this.hass && !this._unsub) this._subscribe();
  }

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    this._unsubscribe();
    window.clearTimeout(this._clock);
    this._clock = undefined;
  }

  /** Only re-render for relevant changes (DESIGN C3): rules come via websocket. */
  protected shouldUpdate(changed: PropertyValues): boolean {
    if (changed.size !== 1 || !changed.has("hass")) return true;
    const old = changed.get("hass") as HomeAssistant | undefined;
    if (!old || !this.hass) return true;
    // The editor's entity / trigger pickers need the current states.
    if (this._editing) return true;
    return (
      old.locale?.language !== this.hass.locale?.language ||
      old.language !== this.hass.language ||
      old.themes?.darkMode !== this.hass.themes?.darkMode ||
      old.user?.is_admin !== this.hass.user?.is_admin
    );
  }

  protected willUpdate(changed: PropertyValues): void {
    if (changed.has("hass") && this.hass) {
      this.toggleAttribute("dark", !!this.hass.themes?.darkMode);
      if (!this._unsub && this.isConnected) this._subscribe();
    }
    if (changed.has("_rules") || changed.has("_config")) this._maybeLoadHistory();
  }

  private _startClock(): void {
    window.clearTimeout(this._clock);
    // Relative texts ("heute", "erinnert 17:00") change with the minute.
    const tick = () => {
      this._now = new Date();
      this._clock = window.setTimeout(tick, 60_000 - (Date.now() % 60_000) + 50);
    };
    this._clock = window.setTimeout(tick, 60_000 - (Date.now() % 60_000) + 50);
  }

  // --- Data -----------------------------------------------------------------

  private _unsubscribe(): void {
    const unsub = this._unsub;
    this._unsub = undefined;
    unsub?.then((fn) => fn()).catch(() => undefined);
  }

  private _subscribe(): void {
    if (!this.hass?.connection) return;
    const unsub = this.hass.connection.subscribeMessage<RuleEvent>(
      (msg) => {
        this._rules = applyRuleEvent(this._rules, msg);
        this._error = undefined;
      },
      { type: "laeutwerk/rules/subscribe" },
    );
    this._unsub = unsub;
    unsub.catch((err) => {
      if (this._unsub !== unsub) return;
      this._unsub = undefined;
      this._error = errorMessage(err);
    });
  }

  /** Reload the history when the shown rule's reminders change. */
  private _maybeLoadHistory(): void {
    if (this._config?.view !== "rule" || !this._config.rule || !this.hass) return;
    const rule = this._rules?.find((r) => r.id === this._config!.rule);
    if (!rule) return;
    const key = JSON.stringify(
      (rule.status?.reminders ?? []).map((r) => [r.id, r.state, r.finished_at]),
    );
    if (key === this._historyKey) return;
    this._historyKey = key;
    this.hass
      .callWS<{ history: HistoryEntry[] }>({
        type: "laeutwerk/history",
        rule_id: rule.id,
        limit: 10,
      })
      .then((res) => (this._history = res.history))
      .catch(() => (this._history = []));
  }

  private get _l(): Localizer {
    return localizer(this.hass?.locale?.language ?? this.hass?.language);
  }

  private get _tz(): string | undefined {
    return this.hass?.config?.time_zone;
  }

  private get _isAdmin(): boolean {
    return !!this.hass?.user?.is_admin;
  }

  private async _call(key: string, service: string, data: Record<string, unknown>): Promise<void> {
    if (!this.hass) return;
    this._busy = key;
    this._actionError = undefined;
    try {
      await this.hass.callService("laeutwerk", service, data);
    } catch (err) {
      this._actionError = this._l.t("failed", { error: errorMessage(err) });
    } finally {
      this._busy = undefined;
    }
  }

  private _done(reminder: Reminder): Promise<void> {
    return this._call(reminder.id, "acknowledge", {
      rule: reminder.rule_id,
      reminder_id: reminder.id,
      ...(this.hass?.user?.name ? { person: this.hass.user.name } : {}),
    });
  }

  private _later(reminder: Reminder): Promise<void> {
    return this._call(`${reminder.id}-later`, "snooze", {
      rule: reminder.rule_id,
      reminder_id: reminder.id,
      duration: "3h",
    });
  }

  private async _toggleRule(rule: Rule): Promise<void> {
    await this._call(`${rule.id}-toggle`, rule.enabled ? "disable" : "enable", { rule: rule.id });
  }

  // --- Render ---------------------------------------------------------------

  protected render() {
    if (!this._config) return nothing;
    const l = this._l;
    if (!this.hass) return html`<ha-card><div class="message">${l.t("loading")}</div></ha-card>`;
    if (this._error) {
      return html`<ha-card>
        <div class="message error">
          <span class="brand">Läutwerk</span>${l.t("not_loaded", { error: this._error })}
        </div>
      </ha-card>`;
    }
    if (!this._rules) return html`<ha-card><div class="message">${l.t("loading")}</div></ha-card>`;
    if (this._editing) {
      return html`<ha-card>
        <laeutwerk-rule-editor
          .hass=${this.hass}
          .localize=${l}
          .rule=${this._editing}
          @saved=${() => (this._editing = undefined)}
          @deleted=${() => (this._editing = undefined)}
          @cancel=${() => (this._editing = undefined)}
        ></laeutwerk-rule-editor>
      </ha-card>`;
    }
    if (this._config.compact) return this._renderCompact();
    if (this._config.view === "rule") return this._renderRuleView();
    return this._renderOverview();
  }

  private _rulesFiltered(): Rule[] {
    const only = this._config?.rules;
    const rules = this._rules ?? [];
    return only?.length ? rules.filter((r) => only.includes(r.id ?? "")) : rules;
  }

  private _renderOverview(
    rules = this._rulesFiltered(),
    extra: TemplateResult | typeof nothing = nothing,
  ): TemplateResult {
    const l = this._l;
    const cfg = this._config!;
    const overview = buildOverview(rules, this._now, this._tz);
    const date = new Intl.DateTimeFormat(l.lang, {
      timeZone: this._tz,
      weekday: "long",
      day: "numeric",
      month: "long",
    }).format(this._now);
    const empty = !overview.open.length;
    return html`<ha-card>
      <div class="head">
        <div class="grow text">
          <div class="date">${date}</div>
          <div class="title">${l.t("title")}</div>
        </div>
        ${
          overview.open.length
            ? html`<span class="chip accent">${l.t("n_open", { n: overview.open.length })}</span>`
            : nothing
        }
        ${
          this._isAdmin
            ? html`<button
                class="mini"
                aria-label=${l.t("new_rule")}
                @click=${() => (this._editing = emptyRule())}
              >
                <ha-icon icon="mdi:plus"></ha-icon>
              </button>`
            : nothing
        }
      </div>
      ${this._actionError ? html`<div class="error">${this._actionError}</div>` : nothing}
      ${
        !this._rules!.length
          ? html`<div class="empty">
              <ha-icon icon="mdi:bell-plus-outline"></ha-icon>
              <div class="name">${l.t("no_rules")}</div>
              <div class="sub">${this._isAdmin ? l.t("no_rules_admin") : ""}</div>
            </div>`
          : empty
            ? html`<div class="empty">
                <ha-icon icon="mdi:check-circle-outline"></ha-icon>
                <div class="name">${l.t("all_done")}</div>
                <div class="sub">${l.t("all_done_sub")}</div>
              </div>`
            : html`<div class="list">
                ${overview.open.map(({ rule, reminder }) => this._openCard(rule, reminder))}
              </div>`
      }
      ${
        cfg.show_upcoming && overview.upcoming.length
          ? html`<div class="separator">${l.t("section_upcoming")}<span class="line"></span></div>
              <div class="list quiet">
                ${overview.upcoming.map(({ rule, reminder }) => this._upcomingRow(rule, reminder))}
              </div>`
          : nothing
      }
      ${
        cfg.show_done && overview.done.length
          ? html`<div class="separator">${l.t("section_done")}<span class="line"></span></div>
              <div class="list quiet">
                ${overview.done.map(({ rule, reminder }) => this._doneRow(rule, reminder))}
              </div>`
          : nothing
      }
      ${extra} ${this._isAdmin && rules.length ? this._rulesList(rules) : nothing}
    </ha-card>`;
  }

  private _icon(rule: Rule, small = false): TemplateResult {
    const color = rule.color ?? "var(--lw-text-2)";
    return html`<span
      class="icon ${small ? "small" : ""}"
      style="background: color-mix(in srgb, ${color} 22%, transparent); color: ${color}"
    >
      <ha-icon .icon=${rule.icon || DEFAULT_ICON}></ha-icon>
    </span>`;
  }

  private _dots(colors: string[] | undefined): TemplateResult | typeof nothing {
    if (!colors?.length) return nothing;
    return html`<span class="dots">
      ${colors.map((c) => html`<span class="dot" style="background:${c}"></span>`)}
    </span>`;
  }

  private _openCard(rule: Rule, reminder: Reminder): TemplateResult {
    const l = this._l;
    const tz = this._tz;
    return html`<div class="rcard active">
      <div class="row">
        ${this._icon(rule)}
        <div class="grow text">
          <div class="name">${reminderTitle(reminder)}</div>
          <div class="sub">${rule.name} · ${relativeDay(reminder.start, this._now, l, tz)}</div>
        </div>
      </div>
      <div class="row meta">
        <span class="chip">${openStatus(reminder, this._now, l, tz)}</span>
        ${this._dots(reminder.colors)}
      </div>
      <div class="actions">
        <button
          class="pill outline"
          ?disabled=${!!this._busy}
          @click=${() => this._later(reminder)}
        >
          ${l.t("later")}
        </button>
        <button class="pill primary" ?disabled=${!!this._busy} @click=${() => this._done(reminder)}>
          <ha-icon icon="mdi:check"></ha-icon>${rule.ack_label || l.t("done")}
        </button>
      </div>
    </div>`;
  }

  private _upcomingRow(rule: Rule, reminder: Reminder): TemplateResult {
    const l = this._l;
    const tz = this._tz;
    const next = reminder.snoozed_until
      ? l.t("snoozed_until", { when: relativeDayTime(reminder.snoozed_until, this._now, l, tz) })
      : reminder.next_reminder_at
        ? l.t("reminder_at", { when: relativeDayTime(reminder.next_reminder_at, this._now, l, tz) })
        : "";
    return html`<div class="row item">
      ${this._icon(rule, true)}
      <div class="grow text">
        <div class="name">${reminder.titles.join(" + ")}</div>
        <div class="sub">${next}</div>
      </div>
      ${this._dots(reminder.colors)}
      <span class="when">${relativeDay(reminder.start, this._now, l, tz)}</span>
    </div>`;
  }

  private _doneRow(rule: Rule, reminder: Reminder): TemplateResult {
    return html`<div class="row item finished">
      ${this._icon(rule, true)}
      <div class="grow text">
        <div class="name ${reminder.state === "done" ? "struck" : ""}">
          ${reminder.titles.join(" + ")}
        </div>
        <div class="sub">${finishedLine(reminder, this._now, this._l, this._tz)}</div>
      </div>
    </div>`;
  }

  private _rulesList(rules: Rule[]): TemplateResult {
    const l = this._l;
    return html`<div class="separator">${l.t("section_rules")}<span class="line"></span></div>
      <div class="list">
        ${rules.map((rule) => {
          const errors = Object.keys(rule.status?.errors ?? {}).length;
          return html`<div class="row item">
            <button class="rulebtn grow" @click=${() => (this._editing = rule)}>
              ${this._icon(rule, true)}
              <span class="grow text">
                <span class="name">${rule.name}</span>
                <span class="sub ${errors ? "bad" : ""}">
                  ${
                    errors
                      ? l.t("rule_error")
                      : rule.enabled
                        ? rule.status?.next_event
                          ? `${rule.status.next_event.titles.join(" + ")} · ${relativeDay(rule.status.next_event.start, this._now, l, this._tz)}`
                          : ""
                        : l.t("rule_off")
                  }
                </span>
              </span>
            </button>
            <button
              class="switch"
              role="switch"
              aria-checked=${rule.enabled}
              aria-label=${rule.name}
              ?disabled=${!!this._busy}
              @click=${() => this._toggleRule(rule)}
            >
              <span></span>
            </button>
          </div>`;
        })}
      </div>`;
  }

  private _renderRuleView(): TemplateResult {
    const l = this._l;
    const id = this._config!.rule;
    if (!id) return html`<ha-card><div class="message">${l.t("no_rule")}</div></ha-card>`;
    const rule = this._rules!.find((r) => r.id === id);
    if (!rule) {
      return html`<ha-card
        ><div class="message">${l.t("rule_missing", { rule: id })}</div></ha-card
      >`;
    }
    return this._renderOverview([rule], this._historySection());
  }

  private _historySection(): TemplateResult {
    const l = this._l;
    const entries = this._history ?? [];
    return html`<div class="separator">${l.t("section_history")}<span class="line"></span></div>
      ${
        entries.length
          ? html`<div class="list quiet">
              ${entries.map(
                (entry) =>
                  html`<div class="row item finished">
                    <span class="icon small hist ${entry.state}">
                      <ha-icon
                        .icon=${entry.state === "done" ? "mdi:check" : "mdi:close"}
                      ></ha-icon>
                    </span>
                    <div class="grow text">
                      <div class="name">${entry.titles.join(" + ")}</div>
                      <div class="sub">
                        ${finishedLine(entry as unknown as Reminder, this._now, l, this._tz)}
                      </div>
                    </div>
                    <span class="when">${formatDate(`${entry.day}T12:00:00`, l, this._tz)}</span>
                  </div>`,
              )}
            </div>`
          : html`<div class="hint">${l.t("history_empty")}</div>`
      }`;
  }

  private _renderCompact(): TemplateResult {
    const l = this._l;
    const overview = buildOverview(this._rulesFiltered(), this._now, this._tz);
    const first = overview.open[0];
    if (!first) {
      const next = overview.upcoming[0];
      return html`<ha-card class="compact">
        <div class="row">
          <span class="icon small"><ha-icon icon="mdi:check-circle-outline"></ha-icon></span>
          <div class="grow text">
            <div class="name">${l.t("all_done")}</div>
            ${
              next
                ? html`<div class="sub">
                    ${next.reminder.titles.join(" + ")} ·
                    ${relativeDay(next.reminder.start, this._now, l, this._tz)}
                  </div>`
                : nothing
            }
          </div>
        </div>
      </ha-card>`;
    }
    const more = overview.open.length - 1;
    return html`<ha-card class="compact">
      <div class="row">
        <span class="badge-wrap">
          ${this._icon(first.rule, true)}
          <span class="badge">${overview.open.length}</span>
        </span>
        <div class="grow text">
          <div class="name">${reminderTitle(first.reminder)}</div>
          ${more > 0 ? html`<div class="sub">${l.t("more_open", { n: more })}</div>` : nothing}
        </div>
        <button
          class="pill primary small"
          ?disabled=${!!this._busy}
          aria-label=${first.rule.ack_label || l.t("done")}
          @click=${() => this._done(first.reminder)}
        >
          <ha-icon icon="mdi:check"></ha-icon>${l.t("done")}
        </button>
      </div>
    </ha-card>`;
  }

  static styles = [
    tokens,
    shared,
    css`
      ha-card {
        display: flex;
        flex-direction: column;
        gap: 12px;
        padding: 14px;
        background: var(--lw-bg);
        border-radius: var(--lw-radius-card);
        box-sizing: border-box;
      }
      ha-card.compact {
        padding: 8px 10px;
        gap: 0;
        justify-content: center;
        height: 100%;
      }
      .message {
        display: flex;
        flex-direction: column;
        gap: 4px;
        padding: 4px 6px;
        font-size: 14px;
        color: var(--lw-text-2);
      }
      .message.error {
        color: var(--lw-danger);
      }
      .brand {
        font-size: 15px;
        font-weight: 600;
        color: var(--lw-text);
      }
      .head {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 2px 2px 0;
      }
      .date {
        font-size: 13px;
        color: var(--lw-text-2);
      }
      .title {
        font-size: 20px;
        font-weight: 700;
      }
      .rcard {
        display: flex;
        flex-direction: column;
        gap: 10px;
        padding: 12px;
        border-radius: 22px;
        background: var(--lw-surface);
        border: 1px solid var(--lw-border);
      }
      .rcard.active {
        border-color: color-mix(in srgb, var(--lw-accent) 55%, transparent);
      }
      .text {
        display: flex;
        flex-direction: column;
        gap: 2px;
        min-width: 0;
      }
      .meta {
        flex-wrap: wrap;
        gap: 8px;
      }
      .dots {
        display: inline-flex;
        gap: 4px;
      }
      .dot {
        width: 10px;
        height: 10px;
        border-radius: 5px;
        box-shadow: 0 0 0 1px var(--lw-border);
      }
      .item {
        min-height: 48px;
      }
      .when {
        font-size: 13px;
        color: var(--lw-text-2);
        white-space: nowrap;
      }
      .struck {
        text-decoration: line-through;
        color: var(--lw-text-2);
      }
      .finished .icon {
        opacity: 0.6;
      }
      .empty {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 4px;
        padding: 18px 12px;
        text-align: center;
        border-radius: 22px;
        background: var(--lw-surface);
      }
      .empty ha-icon {
        --mdc-icon-size: 32px;
        color: var(--lw-ok);
        margin-bottom: 4px;
      }
      .empty .sub {
        white-space: normal;
      }
      .rulebtn {
        display: flex;
        align-items: center;
        gap: 10px;
        text-align: left;
        min-height: 48px;
      }
      .bad {
        color: var(--lw-danger);
      }
      .badge-wrap {
        position: relative;
        display: inline-flex;
      }
      .badge {
        position: absolute;
        top: -4px;
        right: -4px;
        min-width: 18px;
        height: 18px;
        padding: 0 4px;
        border-radius: 9px;
        background: var(--lw-danger);
        color: #fff;
        font-size: 11px;
        font-weight: 700;
        display: flex;
        align-items: center;
        justify-content: center;
        box-sizing: border-box;
      }
      .hist.done {
        color: var(--lw-ok);
      }
      .hist.missed {
        color: var(--lw-danger);
      }
      .pill.small {
        min-height: 44px;
        padding: 0 14px;
      }
    `,
  ];
}

export { CARD_VERSION };

void defineElements([
  ["laeutwerk-card", LaeutwerkCard],
  ["laeutwerk-rule-editor", LaeutwerkRuleEditor],
  ["laeutwerk-signal-editor", LaeutwerkSignalEditor],
  ["laeutwerk-field", LaeutwerkField],
  ["laeutwerk-card-editor", LaeutwerkCardEditor],
]);

declare global {
  interface Window {
    customCards?: Array<{ type: string; name: string; description: string; preview?: boolean }>;
  }
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "laeutwerk-card")) {
  window.customCards.push({
    type: "laeutwerk-card",
    name: "Läutwerk",
    description: "Reminders from calendar events that stay open until acknowledged",
    preview: false,
  });
}

console.info(`%c LÄUTWERK-CARD %c ${CARD_VERSION} `, "background:#222;color:#fff", "");
