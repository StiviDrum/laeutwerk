/** Panel tab "Week": planned reminders of all active rules for the next seven days. */
import { LitElement, css, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import { formatTime } from "./format";
import type { Localizer } from "./localize";
import { shared, tokens } from "./styles";
import type { HomeAssistant, PreviewResult, Rule } from "./types";
import { groupWeek, itemsOf, timedRules, triggerRules, type WeekItem } from "./week-logic";

export class LaeutwerkWeek extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @property({ attribute: false }) public localize!: Localizer;
  @property({ attribute: false }) public rules: Rule[] = [];
  @state() private _items?: WeekItem[];
  @state() private _error?: string;
  private _key = "";

  protected willUpdate(changed: PropertyValues): void {
    if ((changed.has("hass") || changed.has("rules")) && this.hass) {
      const key = JSON.stringify(timedRules(this.rules).map((r) => [r.id, r.name]));
      if (key !== this._key) {
        this._key = key;
        void this._load();
      }
    }
  }

  private async _load(): Promise<void> {
    const hass = this.hass;
    if (!hass) return;
    const all: WeekItem[] = [];
    let failed: string | undefined;
    await Promise.all(
      timedRules(this.rules).map(async (rule) => {
        try {
          const res = await hass.callWS<PreviewResult>({
            type: "laeutwerk/preview",
            rule_id: rule.id,
            limit: 10,
            days: 7,
            passes: 20,
          });
          all.push(...itemsOf(rule, res.passes ?? [], res.events));
        } catch (err) {
          failed = String((err as { message?: string })?.message ?? err);
        }
      }),
    );
    this._items = all;
    this._error = failed;
  }

  private _open(id: string): void {
    this.dispatchEvent(new CustomEvent("open-rule", { detail: id }));
  }

  private _dayLabel(day: string, i: number): string {
    const l = this.localize;
    const d = new Date(`${day}T12:00:00Z`);
    const text = `${l.weekdayShort((d.getUTCDay() + 6) % 7)} ${d.getUTCDate()}.${d.getUTCMonth() + 1}.`;
    return i === 0 ? `${l.t("week_today")}, ${text}` : text;
  }

  protected render(): TemplateResult {
    const l = this.localize;
    if (!this._items) return html`<div class="message">${l.t("loading")}</div>`;
    const tz = this.hass?.config?.time_zone;
    const days = groupWeek(this._items, new Date(), tz);
    const triggers = triggerRules(this.rules);
    return html`<div class="week">
      ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
      <div class="days">
        ${days.map(
          (d, i) =>
            html`<section class="day ${i === 0 ? "today" : ""}">
              <div class="dh">${this._dayLabel(d.day, i)}</div>
              ${
                d.items.length
                  ? d.items.map(
                      (it) =>
                        html`<button class="item" @click=${() => this._open(it.ruleId)}>
                          <span class="t">${formatTime(it.at, tz)}</span>
                          <span class="x"
                            ><span class="title">${it.title}</span
                            ><span class="sub"
                              >${it.ruleName}${it.snoozed ? ` · ${l.t("week_snoozed")}` : ""}${it.followUp ? ` · ${l.t("week_followup")}` : ""}</span
                            ></span
                          >
                        </button>`,
                    )
                  : html`<span class="none">–</span>`
              }
            </section>`,
        )}
      </div>
      ${
        !this._items.length && !triggers.length
          ? html`<div class="message">${l.t("week_none")}</div>`
          : nothing
      }
      ${
        triggers.length
          ? html`<div class="separator">${l.t("week_triggers")}<span class="line"></span></div>
              <div class="hint">${l.t("week_triggers_hint")}</div>
              <div class="wrap">
                ${triggers.map(
                  (r) =>
                    html`<button class="chip" @click=${() => this._open(r.id ?? "")}>
                      <ha-icon .icon=${r.icon || "mdi:bell-ring-outline"}></ha-icon>${r.name}
                    </button>`,
                )}
              </div>`
          : nothing
      }
    </div>`;
  }

  static styles = [
    tokens,
    shared,
    css`
      .week {
        display: flex;
        flex-direction: column;
        gap: 12px;
        padding: 16px;
      }
      .days {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
        gap: 10px;
      }
      .day {
        display: flex;
        flex-direction: column;
        gap: 6px;
        padding: 10px;
        border-radius: 18px;
        background: var(--lw-surface);
        min-width: 0;
      }
      .day.today {
        box-shadow: inset 0 0 0 1.5px var(--lw-accent, var(--primary-color));
      }
      .dh {
        font-weight: 600;
        font-size: 13px;
      }
      .item {
        display: flex;
        gap: 8px;
        min-height: 44px;
        align-items: center;
        text-align: left;
        padding: 4px 8px;
        border-radius: 12px;
        background: transparent;
        width: 100%;
      }
      .t {
        font-variant-numeric: tabular-nums;
        font-weight: 600;
      }
      .x {
        display: flex;
        flex-direction: column;
        min-width: 0;
      }
      .title {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .sub {
        font-size: 12px;
        color: var(--lw-muted, var(--secondary-text-color));
      }
      .none {
        color: var(--lw-muted, var(--secondary-text-color));
        padding: 4px 8px;
      }
      .message {
        padding: 24px;
        text-align: center;
        color: var(--lw-muted, var(--secondary-text-color));
      }
    `,
  ];
}
