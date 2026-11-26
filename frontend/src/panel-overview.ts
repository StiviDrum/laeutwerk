/** Panel tab "Overview": tiles, open reminders, the next 14 days. */
import { LitElement, css, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import { badgeIcon, badgeIconStyles } from "./badge-icon";
import { countSince } from "./event-log";
import { fetchEvents } from "./event-view";
import {
  buildOverview,
  doneLabel,
  liveHeadline,
  openStatus,
  relativeDay,
  relativeDayTime,
  reminderTitle,
  snoozedText,
  statusPill,
} from "./format";
import { healthOf } from "./health";
import type { Localizer, StringKey } from "./localize";
import type { SnoozeData } from "./snooze";
import { shared, tokens } from "./styles";
import type { HomeAssistant, LogEvent, Reminder, Rule } from "./types";

const DAY = 86400_000;

export class LaeutwerkOverview extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @property({ attribute: false }) public localize!: Localizer;
  @property({ attribute: false }) public rules: Rule[] = [];
  @state() private _events: LogEvent[] = [];
  @state() private _laterFor?: string;
  @state() private _now = new Date();
  @state() private _error?: string;
  private _timer?: number;
  private _clock?: number;

  public connectedCallback(): void {
    super.connectedCallback();
    this._clock = window.setInterval(() => (this._now = new Date()), 30_000);
  }

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    window.clearInterval(this._clock);
    window.clearTimeout(this._timer);
  }

  protected willUpdate(changed: PropertyValues): void {
    if (changed.has("rules") && this.hass) {
      // Status changes (acknowledged, missed …) show up in the counters shortly after.
      window.clearTimeout(this._timer);
      this._timer = window.setTimeout(() => void this._load(), changed.get("rules") ? 1200 : 0);
    }
  }

  private async _load(): Promise<void> {
    if (!this.hass) return;
    try {
      const since = new Date(Date.now() - 7 * DAY).toISOString();
      this._events = await fetchEvents(this.hass, {
        since,
        kinds: ["acknowledged", "missed"],
        limit: 1000,
      });
    } catch {
      this._events = [];
    }
  }

  private get _tz(): string | undefined {
    return this.hass?.config?.time_zone;
  }

  private async _call(service: string, data: Record<string, unknown>): Promise<void> {
    this._error = undefined;
    try {
      await this.hass?.callService("laeutwerk", service, data);
    } catch (err) {
      const msg = err && typeof err === "object" && "message" in err ? err.message : err;
      this._error = this.localize.t("failed", { error: String(msg) });
    }
  }

  private _later(reminder: Reminder, when: SnoozeData): void {
    this._laterFor = undefined;
    void this._call("snooze", { rule: reminder.rule_id, reminder_id: reminder.id, ...when });
  }

  private _go(tab: string): void {
    this.dispatchEvent(new CustomEvent("navigate", { detail: tab }));
  }

  protected render(): TemplateResult {
    const l = this.localize;
    const now = this._now;
    const tz = this._tz;
    const overview = buildOverview(this.rules, now, tz);
    const planned = overview.upcoming
      .flatMap(({ rule, reminder }) => {
        const at = reminder.snoozed_until ?? reminder.next_reminder_at;
        return at ? [{ rule, reminder, at }] : [];
      })
      .sort((a, b) => a.at.localeCompare(b.at));
    const nextReminder = planned[0];
    const week = countSince(this._events, now.getTime() - 7 * DAY);
    const hints = this.hass
      ? this.rules.reduce((n, r) => n + healthOf(r, this.hass!).length, 0)
      : 0;
    const horizon = now.getTime() + 14 * DAY;
    const next14 = overview.upcoming.filter(
      ({ reminder }) => new Date(reminder.start).getTime() <= horizon,
    );
    return html`<div class="ov">
      <div class="tiles">
        <div class="tile ${overview.open.length ? "hot" : ""}">
          <div class="tv">${overview.open.length}</div>
          <div class="tl">${l.t("ov_open_now")}</div>
        </div>
        <div class="tile">
          <div class="tv small">
            ${nextReminder ? relativeDayTime(nextReminder.at, now, l, tz) : "–"}
          </div>
          <div class="tl">
            ${l.t("ov_next_reminder")}${
              nextReminder ? html` · ${reminderTitle(nextReminder.reminder)}` : nothing
            }
          </div>
        </div>
        <div class="tile">
          <div class="tv">${week.acknowledged} / ${week.missed}</div>
          <div class="tl">${l.t("ov_week")}</div>
        </div>
        <button class="tile link ${hints ? "warn" : ""}" @click=${() => this._go("health")}>
          <div class="tv small">
            ${hints ? l.t("ov_hints_n", { n: hints }) : l.t("ov_hints_none")}
          </div>
          <div class="tl">${l.t("ov_hints")}</div>
        </button>
      </div>
      ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
      <div class="separator">${l.t("ov_list_open")}<span class="line"></span></div>
      ${
        overview.open.length
          ? html`<div class="stack">
              ${overview.open.map(({ rule, reminder }) => this._openRow(rule, reminder))}
            </div>`
          : html`<div class="hint">${l.t("ov_none_open")}</div>`
      }
      <div class="separator">${l.t("ov_next14")}<span class="line"></span></div>
      ${
        next14.length
          ? html`<div class="stack quiet">
              ${next14.map(({ rule, reminder }) => this._nextRow(rule, reminder))}
            </div>`
          : html`<div class="hint">${l.t("ov_none_next")}</div>`
      }
    </div>`;
  }

  private _pill(reminder: Reminder): TemplateResult {
    const kind = statusPill(reminder);
    return html`<span class="chip ${kind === "due" ? "accent" : ""}"
      >${this.localize.t(`pill_${kind}` as StringKey)}</span
    >`;
  }

  private _openRow(rule: Rule, reminder: Reminder): TemplateResult {
    const l = this.localize;
    const tz = this._tz;
    return html`<div class="item">
      <div class="row">
        ${badgeIcon(rule, false, reminder)}
        <div class="grow text">
          <div class="name">${liveHeadline(rule, reminder, this._now, l.lang)}</div>
          <div class="sub">${rule.name} · ${openStatus(reminder, this._now, l, tz)}</div>
        </div>
        ${this._pill(reminder)}
      </div>
      ${
        this._laterFor === reminder.id
          ? html`<laeutwerk-snooze-menu
              .hass=${this.hass}
              .localize=${l}
              @snooze=${(e: CustomEvent<SnoozeData>) => this._later(reminder, e.detail)}
              @cancel=${() => (this._laterFor = undefined)}
            ></laeutwerk-snooze-menu>`
          : html`<div class="actions">
              <button class="pill outline" @click=${() => (this._laterFor = reminder.id)}>
                ${l.t("later")}
              </button>
              <button
                class="pill primary"
                @click=${() =>
                  this._call("acknowledge", { rule: reminder.rule_id, reminder_id: reminder.id })}
              >
                ${doneLabel(rule, l)}
              </button>
            </div>`
      }
    </div>`;
  }

  private _nextRow(rule: Rule, reminder: Reminder): TemplateResult {
    const l = this.localize;
    const tz = this._tz;
    const snoozed = snoozedText(reminder, this._now, l, tz);
    const at = reminder.next_reminder_at;
    return html`<div class="row nrow">
      ${badgeIcon(rule, true, reminder)}
      <div class="grow text">
        <div class="name">${reminder.titles.join(" + ")}</div>
        <div class="sub">
          ${rule.name} ·
          ${snoozed || (at ? l.t("reminder_at", { when: relativeDayTime(at, this._now, l, tz) }) : "")}
        </div>
      </div>
      ${this._pill(reminder)}
      <span class="when">${relativeDay(reminder.start, this._now, l, tz)}</span>
    </div>`;
  }

  static styles = [
    tokens,
    shared,
    badgeIconStyles,
    css`
      .ov {
        max-width: 880px;
        margin: 0 auto;
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .tiles {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
        gap: 10px;
      }
      .tile {
        text-align: left;
        padding: 14px 16px;
        border-radius: 22px;
        border: 1px solid var(--lw-border);
        background: var(--lw-surface);
        color: var(--lw-text);
        min-height: 44px;
        box-sizing: border-box;
      }
      .tile.hot {
        border-color: var(--lw-accent);
      }
      .tile.warn {
        border-color: var(--lw-danger);
      }
      .tile.link {
        cursor: pointer;
      }
      .tv {
        font-size: 28px;
        font-weight: 700;
      }
      .tv.small {
        font-size: 18px;
        line-height: 34px;
      }
      .tl {
        font-size: 12px;
        color: var(--lw-text-2);
      }
      .stack {
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .item {
        display: flex;
        flex-direction: column;
        gap: 10px;
        padding: 14px;
        border-radius: var(--lw-radius-card, 26px);
        border: 1px solid var(--lw-accent);
        background: var(--lw-surface);
      }
      .quiet {
        gap: 0;
      }
      .nrow {
        min-height: 52px;
        border-top: 1px solid var(--lw-border);
      }
      .nrow:first-child {
        border-top: 0;
      }
      .when {
        font-size: 12px;
        color: var(--lw-text-2);
        min-width: 70px;
        text-align: right;
      }
      .text {
        display: flex;
        flex-direction: column;
        min-width: 0;
      }
    `,
  ];
}
