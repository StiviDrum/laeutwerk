import { LitElement, css, html, type TemplateResult } from "lit";
import { defineElements } from "./register";
import { CARD_VERSION } from "./version";

export interface LaeutwerkCardConfig {
  type: string;
  view?: "overview" | "rule";
  rule?: string;
  rules?: string[];
  show_upcoming?: boolean;
  show_done?: boolean;
  compact?: boolean;
}

/** Placeholder card (scaffold); the real views arrive with milestone 0.4. */
export class LaeutwerkCard extends LitElement {
  static properties = { hass: { attribute: false }, _config: { state: true } };

  hass?: unknown;
  _config?: LaeutwerkCardConfig;

  static getStubConfig(): Partial<LaeutwerkCardConfig> {
    return { view: "overview" };
  }

  setConfig(config: LaeutwerkCardConfig): void {
    if (!config) throw new Error("Invalid configuration");
    this._config = { view: "overview", ...config };
  }

  getCardSize(): number {
    return 3;
  }

  protected render(): TemplateResult {
    return html`<ha-card><div class="empty">Läutwerk ${CARD_VERSION}</div></ha-card>`;
  }

  static styles = css`
    .empty {
      padding: 24px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }
  `;
}

void defineElements([["laeutwerk-card", LaeutwerkCard]]);

const w = window as unknown as { customCards?: Record<string, unknown>[] };
w.customCards = w.customCards ?? [];
w.customCards.push({
  type: "laeutwerk-card",
  name: "Läutwerk",
  description: "Reminders from calendar events that stay open until acknowledged",
  preview: false,
});
