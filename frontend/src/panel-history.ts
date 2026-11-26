/** Panel tab "History": filters, tiles per rule, timeline of the event log. */
import { LitElement, css, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import { LOG_KINDS, ruleStats, shortDuration } from "./event-log";
import { eventStyles, fetchEvents, renderEventTimeline } from "./event-view";
import type { Localizer, StringKey } from "./localize";
import { shared, tokens } from "./styles";
import type { HomeAssistant, LogEvent, Rule } from "./types";

const DAYS = 30;

export class LaeutwerkHistory extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @property({ attribute: false }) public localize!: Localizer;
  @property({ attribute: false }) public rules: Rule[] = [];
  @state() private _events?: LogEvent[];
  @state() private _error?: string;
  @state() private _rule = "";
  @state() private _kind = "";
  private _loading = false;

  protected willUpdate(changed: PropertyValues): void {
    if (changed.has("hass") && this.hass && !this._events && !this._loading) void this._load();
  }

  private async _load(): Promise<void> {
    if (!this.hass) return;
    this._loading = true;
    try {
      const since = new Date(Date.now() - DAYS * 86400_000).toISOString();
      this._events = await fetchEvents(this.hass, { since, limit: 1000 });
      this._error = undefined;
    } catch (err) {
      this._error = String((err as { message?: string })?.message ?? err);
    } finally {
      this._loading = false;
    }
  }

  protected render(): TemplateResult {
    const l = this.localize;
    if (this._error) return html`<div class="message error">${this._error}</div>`;
    if (!this._events) return html`<div class="message">${l.t("loading")}</div>`;
    const names: Record<string, string> = {};
    for (const r of this.rules) names[r.id ?? ""] = r.name;
    const stats = ruleStats(this._events);
    const shown = this._events.filter(
      (e) => (!this._rule || e.rule_id === this._rule) && (!this._kind || e.kind === this._kind),
    );
    return html`<div class="hist">
      <div class="filters">
        <select
          aria-label=${l.t("history_all_rules")}
          .value=${this._rule}
          @change=${(e: Event) => (this._rule = (e.target as HTMLSelectElement).value)}
        >
          <option value="">${l.t("history_all_rules")}</option>
          ${this.rules.map(
            (r) =>
              html`<option value=${r.id ?? ""} ?selected=${r.id === this._rule}>${r.name}</option>`,
          )}
        </select>
        <select
          aria-label=${l.t("history_all_kinds")}
          .value=${this._kind}
          @change=${(e: Event) => (this._kind = (e.target as HTMLSelectElement).value)}
        >
          <option value="">${l.t("history_all_kinds")}</option>
          ${LOG_KINDS.map(
            (k) =>
              html`<option value=${k} ?selected=${k === this._kind}>
                ${l.t(`ev_${k}` as StringKey)}
              </option>`,
          )}
        </select>
        <button class="mini" aria-label=${l.t("reload")} @click=${() => void this._load()}>
          <ha-icon icon="mdi:refresh"></ha-icon>
        </button>
      </div>
      <div class="tiles">
        ${this.rules
          .filter((r) => stats[r.id ?? ""])
          .map((r) => {
            const s = stats[r.id ?? ""];
            return html`<div class="tile">
              <div class="tn">${r.name}</div>
              <div class="tv">
                ${s.acknowledged} <span>${l.t("history_acked")}</span> · ${s.missed}
                <span>${l.t("history_missed")}</span>
              </div>
              ${
                s.avgOpenMinutes !== undefined
                  ? html`<div class="tl">
                      ${l.t("history_avg_open", { time: shortDuration(s.avgOpenMinutes) })}
                    </div>`
                  : nothing
              }
            </div>`;
          })}
      </div>
      ${
        shown.length
          ? renderEventTimeline(shown, l, this.hass?.config?.time_zone, names)
          : html`<div class="hint">${l.t("history_none")}</div>`
      }
    </div>`;
  }

  static styles = [
    tokens,
    shared,
    eventStyles,
    css`
      .hist {
        max-width: 880px;
        margin: 0 auto;
      }
      .message {
        padding: 24px;
        text-align: center;
        color: var(--lw-text-2);
      }
      .filters {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        align-items: center;
      }
      select {
        min-height: 44px;
        border-radius: 22px;
        border: 1px solid var(--lw-border);
        background: var(--lw-surface);
        color: var(--lw-text);
        padding: 0 14px;
        font: inherit;
        flex: 1;
        min-width: 160px;
      }
      .tiles {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
        gap: 10px;
        margin-top: 12px;
      }
      .tile {
        padding: 12px 14px;
        border-radius: 20px;
        border: 1px solid var(--lw-border);
        background: var(--lw-surface);
      }
      .tn {
        font-weight: 600;
      }
      .tv {
        font-size: 20px;
        font-weight: 700;
      }
      .tv span,
      .tl {
        font-size: 12px;
        font-weight: 400;
        color: var(--lw-text-2);
      }
    `,
  ];
}
