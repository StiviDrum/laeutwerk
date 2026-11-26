/** "History of this rule": collapsed card in the rule editor, last 20 events. */
import { LitElement, css, html, nothing, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import { eventStyles, fetchEvents, renderEventList } from "./event-view";
import type { Localizer } from "./localize";
import { shared, tokens } from "./styles";
import type { HomeAssistant, LogEvent } from "./types";

export class LaeutwerkRuleHistory extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @property({ attribute: false }) public localize!: Localizer;
  @property() public ruleId = "";
  @state() private _events?: LogEvent[];
  @state() private _error?: string;
  private _loadedFor = "";

  private _toggle(e: Event): void {
    if (!(e.target as HTMLDetailsElement).open || !this.hass) return;
    if (this._loadedFor === this.ruleId && !this._error) return;
    this._loadedFor = this.ruleId;
    this._error = undefined;
    fetchEvents(this.hass, { rule_id: this.ruleId, limit: 20 })
      .then((events) => (this._events = events))
      .catch((err) => (this._error = String(err?.message ?? err)));
  }

  protected render(): TemplateResult | typeof nothing {
    if (!this.ruleId) return nothing;
    const l = this.localize;
    return html`<details @toggle=${this._toggle}>
      <summary>${l.t("history_rule")}</summary>
      ${
        this._error
          ? html`<div class="error">${this._error}</div>`
          : !this._events
            ? html`<div class="hint">${l.t("loading")}</div>`
            : this._events.length
              ? renderEventList(this._events, l, this.hass?.config?.time_zone)
              : html`<div class="hint">${l.t("history_none")}</div>`
      }
    </details>`;
  }

  static styles = [
    tokens,
    shared,
    eventStyles,
    css`
      details {
        border: 1px solid var(--lw-border);
        border-radius: 20px;
        padding: 0 14px;
      }
      summary {
        min-height: 48px;
        display: flex;
        align-items: center;
        cursor: pointer;
        font-weight: 600;
      }
      details[open] summary {
        margin-bottom: 4px;
      }
      details[open] {
        padding-bottom: 10px;
      }
    `,
  ];
}
