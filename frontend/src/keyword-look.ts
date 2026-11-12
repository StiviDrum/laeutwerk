/**
 * Popup (appended to <body>) to set the icon and colour of one keyword.
 * Empty values fall back on the rule's icon and colour.
 */
import { overlayHost } from "./overlay-host";
import { LitElement, css, html, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import { badgeLook } from "./format";
import type { Localizer } from "./localize";
import { shared, tokens } from "./styles";
import type { HomeAssistant } from "./types";

export interface KeywordLookOptions {
  hass?: HomeAssistant;
  localize: Localizer;
  title: string;
  icon: string;
  color: string;
  /** Rule values used when the keyword has none. */
  rule: { icon?: string | null; color?: string | null };
  swatches?: { label: string; color: string }[];
  /** Colour suggested when none is set yet. */
  suggest?: string;
  dark?: boolean;
}

export interface KeywordLook {
  icon: string;
  color: string;
}

export class LaeutwerkKeywordLook extends LitElement {
  @property({ attribute: false }) public options!: KeywordLookOptions;
  public resolve?: (value: KeywordLook | "delete" | null) => void;
  @state() private _icon = "";
  @state() private _color = "";

  private _onKey = (e: KeyboardEvent) => {
    // A colour popup on top handles Escape itself.
    if (e.key === "Escape" && !document.querySelector("laeutwerk-color-popup")) {
      e.stopPropagation();
      this._answer(null);
    }
  };

  public connectedCallback(): void {
    super.connectedCallback();
    this._icon = this.options.icon;
    this._color = this.options.color;
    document.addEventListener("keydown", this._onKey, true);
  }

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    document.removeEventListener("keydown", this._onKey, true);
  }

  private _answer(value: KeywordLook | "delete" | null): void {
    this.resolve?.(value);
    this.remove();
  }

  protected render(): TemplateResult {
    const o = this.options;
    const l = o.localize;
    const look = badgeLook(o.rule, { icon: this._icon, color: this._color });
    const color = look.color ?? "var(--lw-text-2)";
    return html`<div class="backdrop" @click=${() => this._answer(null)}></div>
      <div class="box" role="dialog" aria-modal="true" aria-label=${o.title}>
        <div class="head">
          <span
            class="badge"
            style="background: color-mix(in srgb, ${color} 22%, transparent); color: ${color}"
            ><ha-icon .icon=${look.icon}></ha-icon
          ></span>
          <div class="title">${o.title}</div>
        </div>
        <div class="row">
          <laeutwerk-field
            class="grow"
            .hass=${o.hass}
            .localize=${l}
            .label=${l.t("keyword_icon")}
            .selector=${{ icon: {} }}
            .value=${this._icon}
            @value-changed=${(e: CustomEvent<{ value: string }>) =>
              (this._icon = e.detail.value || "")}
          ></laeutwerk-field>
          ${
            this._icon
              ? html`<button
                  class="mini"
                  aria-label=${l.t("kw_reset_icon")}
                  title=${l.t("kw_reset_icon")}
                  @click=${() => (this._icon = "")}
                >
                  <ha-icon icon="mdi:close"></ha-icon>
                </button>`
              : ""
          }
        </div>
        <div class="row">
          <laeutwerk-field
            class="grow"
            .hass=${o.hass}
            .localize=${l}
            .label=${l.t("color")}
            .selector=${{ color_rgb: {} }}
            .swatches=${o.swatches ?? []}
            .suggest=${o.suggest ?? ""}
            .value=${this._color}
            @value-changed=${(e: CustomEvent<{ value: string }>) =>
              (this._color = e.detail.value || "")}
          ></laeutwerk-field>
        </div>
        <div class="hint">${l.t("kw_look_hint")}</div>
        <button class="pill danger del" @click=${() => this._answer("delete")}>
          <ha-icon icon="mdi:delete-outline"></ha-icon>${l.t("kw_delete")}
        </button>
        <div class="actions">
          <button class="pill outline" @click=${() => this._answer(null)}>${l.t("cancel")}</button>
          <button
            class="pill primary"
            @click=${() => this._answer({ icon: this._icon, color: this._color })}
          >
            ${l.t("apply")}
          </button>
        </div>
      </div>`;
  }

  static styles = [
    tokens,
    shared,
    css`
      :host {
        position: fixed;
        inset: 0;
        z-index: 1001;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 16px;
        box-sizing: border-box;
      }
      .backdrop {
        position: absolute;
        inset: 0;
        background: rgba(0, 0, 0, 0.55);
      }
      .box {
        position: relative;
        width: 100%;
        max-width: 360px;
        max-height: 100%;
        overflow-y: auto;
        box-sizing: border-box;
        padding: 18px;
        border-radius: var(--lw-radius-card);
        background: var(--lw-bg);
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      .head {
        display: flex;
        align-items: center;
        gap: 12px;
      }
      .badge {
        width: 44px;
        height: 44px;
        border-radius: 22px;
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .badge ha-icon {
        --mdc-icon-size: 24px;
      }
      .title {
        font-size: 17px;
        font-weight: 700;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .mini {
        width: 44px;
        height: 44px;
        flex-shrink: 0;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        color: var(--lw-text-2);
      }
    `,
  ];
}

/** Open the popup; resolves the new icon/colour ("" = reset), "delete" or null (cancelled). */
export function editKeywordLook(
  options: KeywordLookOptions,
): Promise<KeywordLook | "delete" | null> {
  return new Promise((resolve) => {
    const popup = document.createElement("laeutwerk-keyword-look") as LaeutwerkKeywordLook;
    popup.options = options;
    popup.resolve = resolve;
    popup.toggleAttribute("dark", !!options.dark);
    overlayHost().appendChild(popup);
  });
}
