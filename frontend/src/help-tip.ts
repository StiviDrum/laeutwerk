/**
 * Small "?" icon with an explanation. Hover/focus shows the text, a click
 * or tap keeps it open; outside click or Escape closes it.
 * The bubble is `position: fixed` so scroll containers do not clip it.
 */
import { LitElement, css, html, nothing, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import type { Localizer, StringKey } from "./localize";
import { tokens } from "./styles";

export class LaeutwerkHelpTip extends LitElement {
  @property() public text = "";
  @property() public label = "";
  @state() private _open = false;
  @state() private _pos = { left: 12, top: 0, width: 280 };
  private _pinned = false;

  public connectedCallback(): void {
    super.connectedCallback();
    document.addEventListener("pointerdown", this._outside, true);
    document.addEventListener("keydown", this._key, true);
    window.addEventListener("scroll", this._place, true);
    window.addEventListener("resize", this._place);
  }

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    document.removeEventListener("pointerdown", this._outside, true);
    document.removeEventListener("keydown", this._key, true);
    window.removeEventListener("scroll", this._place, true);
    window.removeEventListener("resize", this._place);
  }

  private _outside = (e: Event): void => {
    if (this._open && !e.composedPath().includes(this)) this._set(false);
  };

  private _key = (e: KeyboardEvent): void => {
    if (this._open && e.key === "Escape") {
      e.stopPropagation();
      this._set(false);
    }
  };

  private _set(open: boolean, pinned = false): void {
    this._open = open;
    this._pinned = open && pinned;
    if (open) this._place();
  }

  private _place = (): void => {
    if (!this._open) return;
    const rect = this.getBoundingClientRect();
    const width = Math.min(280, window.innerWidth - 24);
    const left = Math.max(
      12,
      Math.min(rect.left + rect.width / 2 - width / 2, window.innerWidth - width - 12),
    );
    this._pos = { left, top: rect.bottom - 6, width };
  };

  private _hoverable(): boolean {
    return typeof matchMedia === "function" && matchMedia("(hover: hover)").matches;
  }

  private _click(): void {
    if (this._open && !this._pinned) this._set(true, true);
    else this._set(!this._open, true);
  }

  protected render(): TemplateResult {
    const { left, top, width } = this._pos;
    return html`<button
        type="button"
        class="tip"
        aria-label=${this.label || "?"}
        aria-expanded=${this._open}
        @click=${this._click}
        @focus=${() => !this._open && this._set(true)}
        @blur=${() => !this._pinned && this._set(false)}
        @mouseenter=${() => this._hoverable() && !this._open && this._set(true)}
        @mouseleave=${() => !this._pinned && this._set(false)}
      >
        <span class="circle">?</span>
      </button>
      ${
        this._open
          ? html`<div
              class="bubble"
              role="tooltip"
              style="left:${left}px;top:${top}px;width:${width}px"
            >
              ${this.text}
            </div>`
          : nothing
      }`;
  }

  static styles = [
    tokens,
    css`
      :host {
        display: inline-flex;
        vertical-align: middle;
        /* The touch target is 44 px, but it must not widen the row. */
        margin: -10px -8px;
      }
      .tip {
        width: 44px;
        height: 44px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        color: var(--lw-text-2);
      }
      .circle {
        width: 24px;
        height: 24px;
        box-sizing: border-box;
        border-radius: 12px;
        border: 1.5px solid currentColor;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 13px;
        font-weight: 700;
        line-height: 1;
      }
      .tip[aria-expanded="true"] .circle {
        color: var(--lw-accent);
      }
      .bubble {
        position: fixed;
        z-index: 1002;
        box-sizing: border-box;
        padding: 10px 12px;
        border-radius: 16px;
        border: 1px solid var(--lw-border);
        background: var(--lw-bg);
        color: var(--lw-text);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
        font-size: 13px;
        font-weight: 400;
        line-height: 1.45;
        white-space: pre-line;
      }
    `,
  ];
}

/** `<laeutwerk-help-tip>` with a localised text. */
export function helpTip(l: Localizer, key: StringKey): TemplateResult {
  return html`<laeutwerk-help-tip .text=${l.t(key)} .label=${l.t("help")}></laeutwerk-help-tip>`;
}
