/**
 * Small "?" icon with an explanation. Hover/focus shows the text, a click
 * or tap keeps it open; outside click or Escape closes it.
 * The bubble is a body-level popover (top layer), so neither scroll containers nor
 * stacking contexts (sticky cells) can clip or cover it.
 */
import { LitElement, css, html, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import type { Localizer, StringKey } from "./localize";
import { tokens } from "./styles";

export class LaeutwerkHelpTip extends LitElement {
  @property() public text = "";
  @property() public label = "";
  @state() private _open = false;
  private _pinned = false;
  private _bubble?: HTMLElement;

  public connectedCallback(): void {
    super.connectedCallback();
    document.addEventListener("pointerdown", this._outside, true);
    document.addEventListener("keydown", this._key, true);
    window.addEventListener("scroll", this._onScroll, true);
    window.addEventListener("resize", this._onResize);
  }

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    document.removeEventListener("pointerdown", this._outside, true);
    document.removeEventListener("keydown", this._key, true);
    window.removeEventListener("scroll", this._onScroll, true);
    window.removeEventListener("resize", this._onResize);
    this._set(false);
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

  private _onScroll = (e: Event): void => {
    // Scrolling inside the bubble itself keeps it open.
    if (this._open && e.target !== this._bubble) this._set(false);
  };

  private _onResize = (): void => {
    if (this._open) this._set(false);
  };

  private _set(open: boolean, pinned = false): void {
    this._open = open;
    this._pinned = open && pinned;
    if (open) this._show();
    else this._hide();
  }

  private _hide(): void {
    const b = this._bubble as (HTMLElement & { hidePopover?: () => void }) | undefined;
    try {
      b?.hidePopover?.();
    } catch {
      /* not shown as popover */
    }
    b?.remove();
    this._bubble = undefined;
  }

  /** The bubble lives on `document.body`, so no stacking context can cover it. */
  private _show(): void {
    this._hide();
    const rect = this.getBoundingClientRect();
    const cs = getComputedStyle(this);
    const v = (name: string, fallback: string): string =>
      cs.getPropertyValue(name).trim() || fallback;
    const width = Math.min(280, window.innerWidth - 24);
    const left = Math.max(
      12,
      Math.min(rect.left + rect.width / 2 - width / 2, window.innerWidth - width - 12),
    );
    const el = document.createElement("div");
    el.setAttribute("role", "tooltip");
    el.textContent = this.text;
    el.style.cssText =
      `position:fixed;inset:auto;margin:0;overflow:visible;z-index:1010;box-sizing:border-box;left:${left}px;top:${rect.bottom - 6}px;` +
      `width:${width}px;padding:10px 12px;border-radius:16px;` +
      `border:1px solid ${v("--lw-border", "rgba(127,127,127,0.35)")};` +
      `background:${v("--lw-bg", "var(--card-background-color, #fff)")};` +
      `color:${v("--lw-text", "var(--primary-text-color, #111)")};` +
      "box-shadow:0 8px 24px rgba(0,0,0,0.35);font:400 13px/1.45 system-ui,sans-serif;" +
      "white-space:pre-line;pointer-events:none";
    // Popover API: top layer, so it also sits above HA's dialogs.
    const pop = el as HTMLElement & { showPopover?: () => void };
    if (typeof pop.showPopover === "function") el.setAttribute("popover", "manual");
    document.body.appendChild(el);
    if (el.hasAttribute("popover")) {
      try {
        pop.showPopover?.();
      } catch {
        /* falls back to the plain body element */
      }
    }
    this._bubble = el;
  }

  private _hoverable(): boolean {
    return typeof matchMedia === "function" && matchMedia("(hover: hover)").matches;
  }

  private _click(): void {
    if (this._open && !this._pinned) this._set(true, true);
    else this._set(!this._open, true);
  }

  protected updated(): void {
    if (this._bubble) this._bubble.textContent = this.text;
  }

  protected render(): TemplateResult {
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
    </button>`;
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
    `,
  ];
}

/** `<laeutwerk-help-tip>` with a localised text. */
export function helpTip(l: Localizer, key: StringKey): TemplateResult {
  return html`<laeutwerk-help-tip .text=${l.t(key)} .label=${l.t("help")}></laeutwerk-help-tip>`;
}
