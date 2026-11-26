/** "Remind me later" menu shared by the card, the compact dialog and the panel. */
import { LitElement, css, html, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import type { Localizer } from "./localize";
import { currentPerson, snoozeChoices, type SnoozeData } from "./snooze";
import { shared, tokens } from "./styles";
import type { HomeAssistant } from "./types";

export class LaeutwerkSnoozeMenu extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @property({ attribute: false }) public localize!: Localizer;
  @property({ type: Boolean }) public busy = false;
  @state() private _time = false;
  @state() private _value = "";

  private _pick(data: SnoozeData): void {
    this.dispatchEvent(new CustomEvent("snooze", { detail: data, bubbles: true, composed: true }));
  }

  private _cancel(): void {
    this._time = false;
    this.dispatchEvent(new CustomEvent("cancel", { bubbles: true, composed: true }));
  }

  protected render(): TemplateResult {
    const l = this.localize;
    if (this._time) {
      return html`<div class="menu">
        <input
          type="time"
          aria-label=${l.t("later_until")}
          .value=${this._value}
          @input=${(e: Event) => (this._value = (e.target as HTMLInputElement).value)}
        />
        <button
          class="pill primary"
          ?disabled=${this.busy || !this._value}
          @click=${() => this._pick({ until: this._value })}
        >
          ${l.t("ok")}
        </button>
        <button class="mini" aria-label=${l.t("cancel")} @click=${() => (this._time = false)}>
          <ha-icon icon="mdi:close"></ha-icon>
        </button>
      </div>`;
    }
    const choices = snoozeChoices(
      new Date(),
      this.hass?.config?.time_zone,
      currentPerson(this.hass),
    );
    return html`<div class="menu">
      ${choices.map(
        (c) =>
          html`<button
            class="pill outline"
            ?disabled=${this.busy}
            @click=${() => this._pick(c.data)}
          >
            ${l.t(c.key)}
          </button>`,
      )}
      <button class="pill outline" ?disabled=${this.busy} @click=${() => (this._time = true)}>
        ${l.t("later_until")}
      </button>
      <button class="mini" aria-label=${l.t("cancel")} @click=${() => this._cancel()}>
        <ha-icon icon="mdi:close"></ha-icon>
      </button>
    </div>`;
  }

  static styles = [
    tokens,
    shared,
    css`
      :host {
        display: block;
      }
      .menu {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        align-items: center;
      }
      .menu .pill {
        flex: 1 1 auto;
        min-width: 0;
        min-height: 44px;
        padding: 0 12px;
        font-size: 13px;
      }
      input {
        min-height: 44px;
        flex: 1;
        box-sizing: border-box;
        border-radius: 22px;
        border: 1px solid var(--lw-border);
        background: transparent;
        color: inherit;
        padding: 0 14px;
        font: inherit;
      }
    `,
  ];
}
