/**
 * laeutwerk-card: "Heute & demnächst" overview, single rule view, compact
 * line and the rule editor (DESIGN.md C1).
 */
import { badgeIcon, badgeIconStyles } from "./badge-icon";
import { overlayHost } from "./overlay-host";
import { LitElement, css, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import {
  assigneeText,
  buildOverview,
  doneLabel,
  canReopen,
  finishedLine,
  formatDate,
  isAhead,
  openStatus,
  relativeDay,
  relativeDayTime,
  reminderTitle,
  tasks,
  tooEarlyText,
} from "./format";
import { LaeutwerkConfirm, confirmAction } from "./confirm-dialog";
import { localizer, type Localizer, type StringKey } from "./localize";
import { defineElements } from "./register";
import type { LaeutwerkTaskDialog } from "./task-dialog";
import { applyRuleEvent } from "./rule-events";
import { shared, tokens } from "./styles";
import type {
  Badge,
  HistoryEntry,
  HomeAssistant,
  LaeutwerkCardConfig,
  Reminder,
  Rule,
  RuleEvent,
} from "./types";
import { CARD_VERSION } from "./version";

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
  /** Short feedback ("Erledigt · Rückgängig", "Gespeichert"). */
  @state() private _toast?: { text: string; undo?: string };
  /** Reminder whose "later" choices are shown / whose details are open. */
  @state() private _laterFor?: string;
  @state() private _details?: string;
  @state() private _sorting = false;
  @state() private _search = "";
  private _toastTimer?: number;
  private _dialog?: LaeutwerkTaskDialog;
  private _dialogLoading = false;
  private _filtered?: { rules: Rule[]; only: string[]; result: Rule[] };
  private _memo?: {
    rules: Rule[];
    now: Date;
    lang: string;
    overview: ReturnType<typeof buildOverview>;
    date: string;
  };
  /** Rule open in the editor (new rule: without id). */
  @state() private _editing?: Rule;
  /** Template picker for a new rule is open. */
  @state() private _picking = false;
  /** The lazy editor chunk is loaded and its elements are defined. */
  @state() private _editorsReady = false;
  private _editorsLoading = false;
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

  public static async getConfigElement(): Promise<HTMLElement> {
    await import("./card-editor-entry").then((m) => m.ready);
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
    this._dialog?.remove();
    this._dialog = undefined;
    this._unsubscribe();
    window.clearTimeout(this._clock);
    this._clock = undefined;
  }

  /** Only re-render for relevant changes (DESIGN C3): rules come via websocket. */
  protected shouldUpdate(changed: PropertyValues): boolean {
    if (this._dialog) {
      this._dialog.hass = this.hass;
      this._dialog.rules = this._rules ?? [];
    }
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

  /** Load the editor chunk on first use (resolves once its elements exist). */
  private _loadEditors(): Promise<void> {
    return import("./editors").then((m) => {
      this._editorsReady = true;
      return m.ready;
    });
  }

  protected willUpdate(changed: PropertyValues): void {
    if ((this._editing || this._picking) && !this._editorsReady && !this._editorsLoading) {
      this._editorsLoading = true;
      this._loadEditors().catch((e) => {
        this._editorsLoading = false;
        this._error = String(e);
      });
    }
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

  private _tooEarly?: string;

  private async _call(
    key: string,
    service: string,
    data: Record<string, unknown>,
    returnResponse = false,
  ): Promise<boolean> {
    if (!this.hass) return false;
    this._busy = key;
    this._actionError = undefined;
    this._tooEarly = undefined;
    try {
      const result = await this.hass.callService(
        "laeutwerk",
        service,
        data,
        undefined,
        undefined,
        returnResponse || undefined,
      );
      if (returnResponse) this._tooEarly = tooEarlyText(result);
      return true;
    } catch (err) {
      this._actionError = this._l.t("failed", { error: errorMessage(err) });
      return false;
    } finally {
      this._busy = undefined;
    }
  }

  private _showToast(text: string, undo?: string): void {
    window.clearTimeout(this._toastTimer);
    this._toast = { text, undo };
    this._toastTimer = window.setTimeout(() => (this._toast = undefined), undo ? 8000 : 3000);
  }

  private _ask(title: string, text: string, confirm: string, icon: string): Promise<boolean> {
    return confirmAction({
      title,
      text,
      confirm,
      cancel: this._l.t("cancel"),
      icon,
      dark: !!this.hass?.themes?.darkMode,
    });
  }

  private async _done(reminder: Reminder, rule?: Rule): Promise<void> {
    const l = this._l;
    const asked = await this._ask(
      reminderTitle(reminder),
      l.t("confirm_done"),
      rule ? doneLabel(rule, l) : l.t("done"),
      "mdi:check",
    );
    if (!asked) return;
    // Who it was is resolved by Läutwerk from the user (person, else name).
    const ok = await this._call(
      reminder.id,
      "acknowledge",
      {
        rule: reminder.rule_id,
        reminder_id: reminder.id,
      },
      true,
    );
    if (ok && this._tooEarly) this._showToast(this._tooEarly);
    else if (ok)
      this._showToast(this._l.t("done_toast", { title: reminderTitle(reminder) }), reminder.id);
  }

  /** Undo from the toast right after "done": no question (it was just done). */
  private async _undo(reminderId: string): Promise<void> {
    window.clearTimeout(this._toastTimer);
    this._toast = undefined;
    await this._call(`${reminderId}-undo`, "reopen", { reminder_id: reminderId });
  }

  /** Reopen a task from the done list – with a question, like in the dialog. */
  private async _reopen(reminder: Reminder): Promise<void> {
    const l = this._l;
    if (
      await this._ask(reminderTitle(reminder), l.t("confirm_reopen"), l.t("reopen"), "mdi:undo")
    ) {
      await this._call(`${reminder.id}-undo`, "reopen", { reminder_id: reminder.id });
    }
  }

  private async _later(reminder: Reminder, choice: "1h" | "3h" | "morning"): Promise<void> {
    this._laterFor = undefined;
    const when = choice === "morning" ? { until: "07:00" } : { duration: choice };
    const ok = await this._call(`${reminder.id}-later`, "snooze", {
      rule: reminder.rule_id,
      reminder_id: reminder.id,
      ...when,
    });
    if (ok) this._showToast(this._l.t("later_toast", { title: reminderTitle(reminder) }));
  }

  private async _move(rule: Rule, delta: number): Promise<void> {
    if (!this.hass || !this._rules) return;
    const ids = this._rules.map((r) => r.id ?? "");
    const from = ids.indexOf(rule.id ?? "");
    const to = from + delta;
    if (from < 0 || to < 0 || to >= ids.length) return;
    [ids[from], ids[to]] = [ids[to], ids[from]];
    try {
      await this.hass.callWS({ type: "laeutwerk/rules/reorder", rule_ids: ids });
    } catch (err) {
      this._actionError = this._l.t("failed", { error: errorMessage(err) });
    }
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
    if ((this._picking || this._editing) && !this._editorsReady) {
      return html`<ha-card><div class="message">${l.t("loading")}</div></ha-card>`;
    }
    if (this._picking) {
      return html`<ha-card>
        <laeutwerk-template-picker
          .hass=${this.hass}
          .localize=${l}
          @pick=${(e: CustomEvent<{ rule: Rule }>) => {
            this._picking = false;
            this._editing = e.detail.rule;
          }}
          @imported=${() => (this._picking = false)}
          @cancel=${() => (this._picking = false)}
        ></laeutwerk-template-picker>
      </ha-card>`;
    }
    if (this._editing) {
      return html`<ha-card>
        <laeutwerk-rule-editor
          .hass=${this.hass}
          .localize=${l}
          .rule=${this._editing}
          @saved=${() => {
            this._editing = undefined;
            this._showToast(l.t("saved"));
          }}
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
    if (!only?.length) return rules;
    const c = this._filtered;
    if (c && c.rules === rules && c.only === only) return c.result;
    const result = rules.filter((r) => only.includes(r.id ?? ""));
    this._filtered = { rules, only, result };
    return result;
  }

  private _renderOverview(
    rules = this._rulesFiltered(),
    extra: TemplateResult | typeof nothing = nothing,
  ): TemplateResult {
    const l = this._l;
    const cfg = this._config!;
    const memo = this._memo;
    if (!memo || memo.rules !== rules || memo.now !== this._now || memo.lang !== l.lang) {
      const date = new Intl.DateTimeFormat(l.lang, {
        timeZone: this._tz,
        weekday: "long",
        day: "numeric",
        month: "long",
      }).format(this._now);
      this._memo = {
        rules,
        now: this._now,
        lang: l.lang,
        overview: buildOverview(rules, this._now, this._tz),
        date,
      };
    }
    const { overview, date } = this._memo!;
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
      </div>
      ${this._actionError ? html`<div class="error">${this._actionError}</div>` : nothing}
      ${this._renderToast()}
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
              <div class="list quiet divided">
                ${overview.upcoming.map(({ rule, reminder }) => this._upcomingRow(rule, reminder))}
              </div>`
          : nothing
      }
      ${
        cfg.show_done && overview.done.length
          ? html`<div class="separator">${l.t("section_done")}<span class="line"></span></div>
              <div class="list quiet divided">
                ${overview.done.map(({ rule, reminder }) => this._doneRow(rule, reminder))}
              </div>`
          : nothing
      }
      ${extra} ${this._isAdmin && rules.length ? this._rulesList(rules) : nothing}
    </ha-card>`;
  }

  private _renderToast(): TemplateResult | typeof nothing {
    const toast = this._toast;
    if (!toast) return nothing;
    return html`<div class="toast" role="status">
      <span class="grow">${toast.text}</span>
      ${
        toast.undo
          ? html`<button class="chip accent" @click=${() => this._undo(toast.undo!)}>
              <ha-icon icon="mdi:undo"></ha-icon>${this._l.t("undo")}
            </button>`
          : nothing
      }
    </div>`;
  }

  /** What happened with a reminder so far and what comes next. */
  private _detailsOf(rule: Rule, reminder: Reminder): TemplateResult {
    const l = this._l;
    const tz = this._tz;
    const at = (iso?: string | null) => (iso ? relativeDayTime(iso, this._now, l, tz) : "–");
    const signalName = (id: string) => {
      const signal = rule.signals.find((x) => x.id === id);
      if (!signal) return id;
      const type = l.t(`type_${signal.type}` as StringKey);
      // The id only helps when a rule has several signals of one type.
      return id === signal.type ? type : `${type} (${id})`;
    };
    const sent = Object.entries(reminder.signals_sent ?? {});
    const deferred = Object.entries(reminder.deferred ?? {});
    const rows: [string, string][] = [
      [l.t("d_event"), `${reminder.titles.join(" + ")} · ${formatDate(reminder.start, l, tz)}`],
    ];
    if (reminder.reminded_at) rows.push([l.t("d_reminded"), at(reminder.reminded_at)]);
    if (reminder.next_reminder_at) rows.push([l.t("d_next"), at(reminder.next_reminder_at)]);
    if (reminder.snoozed_until) rows.push([l.t("later"), at(reminder.snoozed_until)]);
    if (reminder.expires_at) rows.push([l.t("d_expires"), at(reminder.expires_at)]);
    if (reminder.assignee_name)
      rows.push([
        l.t("d_assignee"),
        assigneeText(l, reminder.assignee_name, reminder.substitute_for_name),
      ]);
    if (reminder.stage) rows.push([l.t("d_stage"), String(reminder.stage)]);
    rows.push([
      l.t("d_signals"),
      sent.length
        ? sent
            .map(([id, n]) => `${signalName(id)}: ${n}× (${at(reminder.signal_last?.[id])})`)
            .join(", ")
        : l.t("d_none"),
    ]);
    if (deferred.length) {
      rows.push([
        l.t("d_deferred"),
        deferred.map(([id, when]) => `${signalName(id)}: ${at(when)}`).join(", "),
      ]);
    }
    if (reminder.tags?.length) rows.push([l.t("d_tags"), reminder.tags.join(", ")]);
    return html`<dl class="details">
      ${rows.map(
        ([key, value]) =>
          html`<dt>${key}</dt>
            <dd>${value}</dd>`,
      )}
    </dl>`;
  }

  private _toggleDetails(reminder: Reminder): void {
    this._details = this._details === reminder.id ? undefined : reminder.id;
  }

  private _icon(rule: Rule, small = false, item?: { badges?: Badge[] }): TemplateResult {
    return badgeIcon(rule, small, item);
  }

  private _openCard(rule: Rule, reminder: Reminder): TemplateResult {
    const l = this._l;
    const tz = this._tz;
    const choosing = this._laterFor === reminder.id;
    return html`<div class="rcard active">
      <button
        class="row tap"
        aria-expanded=${this._details === reminder.id}
        @click=${() => this._toggleDetails(reminder)}
      >
        ${this._icon(rule, false, reminder)}
        <div class="grow text">
          <div class="name">${reminderTitle(reminder)}</div>
          <div class="sub">
            ${rule.name} ·
            ${relativeDay(reminder.start, this._now, l, tz)}${
              reminder.assignee_name
                ? html` ·
                  ${l.t("responsible", {
                    name: assigneeText(l, reminder.assignee_name, reminder.substitute_for_name),
                  })}`
                : nothing
            }
          </div>
        </div>
      </button>
      <div class="row meta">
        <span class="chip">${openStatus(reminder, this._now, l, tz)}</span>
      </div>
      ${this._details === reminder.id ? this._detailsOf(rule, reminder) : nothing}
      ${
        choosing
          ? html`<div class="later">
              ${(
                [
                  ["1h", "later_1h"],
                  ["3h", "later_3h"],
                  ["morning", "later_morning"],
                ] as const
              ).map(
                ([choice, key]) =>
                  html`<button
                    class="pill outline"
                    ?disabled=${!!this._busy}
                    @click=${() => this._later(reminder, choice)}
                  >
                    ${l.t(key)}
                  </button>`,
              )}
              <button
                class="mini"
                aria-label=${l.t("cancel")}
                @click=${() => (this._laterFor = undefined)}
              >
                <ha-icon icon="mdi:close"></ha-icon>
              </button>
            </div>`
          : html`<div class="actions">
              <button
                class="pill outline"
                ?disabled=${!!this._busy}
                @click=${() => (this._laterFor = reminder.id)}
              >
                ${l.t("later")}
              </button>
              <button
                class="pill primary"
                aria-label=${doneLabel(rule, l)}
                title=${doneLabel(rule, l)}
                ?disabled=${!!this._busy}
                @click=${() => this._done(reminder, rule)}
              >
                ${this._busy === reminder.id ? "…" : html`<ha-icon icon="mdi:check"></ha-icon>`}
              </button>
            </div>`
      }
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
    return html`<div class="entry">
      <button class="row item tap" @click=${() => this._toggleDetails(reminder)}>
        ${this._icon(rule, true, reminder)}
        <div class="grow text">
          <div class="name">${reminder.titles.join(" + ")}</div>
          <div class="sub">${next}</div>
        </div>
        <span class="when">${relativeDay(reminder.start, this._now, l, tz)}</span>
      </button>
      ${this._details === reminder.id ? this._detailsOf(rule, reminder) : nothing}
    </div>`;
  }

  private _doneRow(rule: Rule, reminder: Reminder): TemplateResult {
    const l = this._l;
    const ahead = isAhead(reminder, this._now);
    return html`<div class="entry">
      <div class="row">
        <button class="row item finished tap grow" @click=${() => this._toggleDetails(reminder)}>
          ${this._icon(rule, true, reminder)}
          <div class="grow text">
            <div class="name ${reminder.state === "done" ? "struck" : ""}">
              ${ahead ? reminderTitle(reminder) : reminder.titles.join(" + ")}
            </div>
            <div class="sub">${finishedLine(reminder, this._now, l, this._tz)}</div>
          </div>
        </button>
        ${
          canReopen(reminder, this._now)
            ? html`<button
                class="mini"
                aria-label=${l.t("undo")}
                title=${l.t("undo")}
                ?disabled=${!!this._busy}
                @click=${() => this._reopen(reminder)}
              >
                <ha-icon icon="mdi:undo"></ha-icon>
              </button>`
            : nothing
        }
      </div>
      ${this._details === reminder.id ? this._detailsOf(rule, reminder) : nothing}
    </div>`;
  }

  private _rulesList(all: Rule[]): TemplateResult {
    const l = this._l;
    const query = this._search.trim().toLowerCase();
    const rules = query ? all.filter((r) => r.name.toLowerCase().includes(query)) : all;
    const canSort = !this._config?.rules?.length && all.length > 1;
    return html`<div class="separator">
        ${l.t("section_rules")}<span class="line"></span>
        ${
          this._isAdmin
            ? html`<button class="chip" @click=${() => (this._picking = true)}>
                <ha-icon icon="mdi:plus"></ha-icon>
                ${l.t("add_rule")}
              </button>`
            : nothing
        }
        ${
          canSort
            ? html`<button class="chip" @click=${() => (this._sorting = !this._sorting)}>
                <ha-icon .icon=${this._sorting ? "mdi:check" : "mdi:sort"}></ha-icon>
                ${this._sorting ? l.t("sort_done") : l.t("sort")}
              </button>`
            : nothing
        }
      </div>
      ${
        all.length > 5 && !this._sorting
          ? html`<input
              class="search"
              type="search"
              placeholder=${l.t("search")}
              aria-label=${l.t("search")}
              .value=${this._search}
              @input=${(e: Event) => (this._search = (e.target as HTMLInputElement).value)}
            />`
          : nothing
      }
      <div class="divided">
        ${rules.map((rule, index) => {
          if (this._sorting) {
            return html`<div class="row item">
              ${this._icon(rule, true)}
              <span class="grow name">${rule.name}</span>
              <button
                class="mini"
                aria-label=${l.t("move_up")}
                ?disabled=${index === 0}
                @click=${() => this._move(rule, -1)}
              >
                <ha-icon icon="mdi:arrow-up"></ha-icon>
              </button>
              <button
                class="mini"
                aria-label=${l.t("move_down")}
                ?disabled=${index === rules.length - 1}
                @click=${() => this._move(rule, 1)}
              >
                <ha-icon icon="mdi:arrow-down"></ha-icon>
              </button>
            </div>`;
          }
          const errors = Object.keys(rule.status?.errors ?? {}).length;
          return html`<div class="row item">
            <button class="rulebtn grow" @click=${() => (this._editing = rule)}>
              ${this._icon(rule, true)}
              <span class="grow text">
                <span class="name"
                  >${rule.name}${rule.visible === false ? html` <ha-icon class="hidden-icon" icon="mdi:eye-off-outline" title=${l.t("visible")}></ha-icon>` : nothing}</span
                >
                <span class="sub ${errors ? "bad" : ""}">
                  ${
                    errors
                      ? l.t("rule_error")
                      : rule.enabled && rule.status?.active === false
                        ? l.t("rule_inactive")
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
          ? html`<div class="list quiet divided">
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

  /** Compact: the next task in one line; tapping opens the task dialog. */
  private _renderCompact(): TemplateResult {
    const l = this._l;
    const all = tasks(this._rules ?? [], this._config?.rules);
    const task = all[0];
    const openCount = all.filter((t) => t.open).length;
    const clickable = !!task || this._isAdmin;
    let line: TemplateResult;
    if (!task) {
      line = html`<span class="icon small"><ha-icon icon="mdi:calendar-check"></ha-icon></span>
        <span class="grow oneline dim">${l.t("no_tasks")}</span>`;
    } else {
      // Planned tasks already say when in their title ("Am Freitag: …").
      const when = task.open ? openStatus(task.reminder, this._now, l, this._tz) : "";
      line = html`<span class="badge-wrap">
          ${this._icon(task.rule, true, task.reminder)}
          ${openCount ? html`<span class="badge">${openCount}</span>` : nothing}
        </span>
        <span class="grow oneline ${task.open ? "" : "dim"}">
          <span class="name">${reminderTitle(task.reminder)}</span>
          ${when ? html`<span class="when"> · ${when}</span>` : nothing}
        </span>`;
    }
    return html`<ha-card
      class="compact ${task?.open ? "due" : ""}"
      role=${clickable ? "button" : nothing}
      tabindex=${clickable ? "0" : nothing}
      aria-label=${task ? reminderTitle(task.reminder) : l.t("no_tasks")}
      @click=${() => clickable && this._openDialog()}
      @keydown=${(e: KeyboardEvent) => {
        if (clickable && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          this._openDialog();
        }
      }}
    >
      <div class="row">
        ${line}
        ${clickable ? html`<ha-icon class="chev" icon="mdi:chevron-right"></ha-icon>` : nothing}
      </div>
    </ha-card>`;
  }

  /** The task dialog lives at <body> level (not clipped by the grid cell). */
  private async _openDialog(): Promise<void> {
    if (this._dialog || this._dialogLoading) return;
    this._dialogLoading = true;
    try {
      await this._loadEditors();
    } finally {
      this._dialogLoading = false;
    }
    if (this._dialog) return;
    const dialog = document.createElement("laeutwerk-task-dialog") as LaeutwerkTaskDialog;
    dialog.hass = this.hass;
    dialog.localize = this._l;
    dialog.rules = this._rules ?? [];
    dialog.only = this._config?.rules ?? [];
    dialog.toggleAttribute("dark", !!this.hass?.themes?.darkMode);
    dialog.addEventListener("closed", () => (this._dialog = undefined));
    overlayHost().appendChild(dialog);
    this._dialog = dialog;
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
      .hidden-icon {
        --mdc-icon-size: 14px;
        color: var(--lw-text-2);
        vertical-align: -2px;
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
      ${badgeIconStyles}
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
      .toast {
        display: flex;
        align-items: center;
        gap: 10px;
        min-height: 44px;
        padding: 4px 6px 4px 14px;
        border-radius: 22px;
        background: var(--lw-surface-2);
        font-size: 14px;
      }
      .tap {
        width: 100%;
        text-align: left;
      }
      .entry {
        display: flex;
        flex-direction: column;
      }
      .details {
        display: grid;
        grid-template-columns: max-content 1fr;
        gap: 4px 12px;
        margin: 0;
        padding: 10px 12px;
        border-radius: 14px;
        background: var(--lw-surface);
        font-size: 13px;
      }
      .details dt {
        color: var(--lw-text-2);
      }
      .details dd {
        margin: 0;
        min-width: 0;
        overflow-wrap: anywhere;
      }
      .later {
        display: flex;
        gap: 6px;
        align-items: center;
      }
      .later .pill {
        flex: 1;
        min-width: 0;
        padding: 0 8px;
        font-size: 13px;
      }
      .search {
        min-height: 40px;
      }
      .separator .chip {
        min-height: 32px;
      }
      ha-card.compact {
        cursor: pointer;
        min-height: 56px;
      }
      ha-card.compact.due {
        border: 1px solid color-mix(in srgb, var(--lw-accent) 55%, transparent);
      }
      ha-card.compact:focus-visible {
        outline: 2px solid var(--lw-accent);
        outline-offset: 2px;
      }
      .oneline {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        font-size: 15px;
      }
      .oneline .name {
        font-weight: 600;
      }
      .oneline .when {
        color: var(--lw-text-2);
        font-size: 13px;
      }
      .oneline.dim .name {
        font-weight: 500;
        color: var(--lw-text-2);
      }
      .chev {
        color: var(--lw-text-2);
      }
      .actions .pill.primary ha-icon {
        --mdc-icon-size: 24px;
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
  ["laeutwerk-confirm", LaeutwerkConfirm],
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
