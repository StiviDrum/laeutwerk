/**
 * Small confirmation popup ("Als erledigt markieren?") on top of everything.
 * Appended to <body> so dashboards and other dialogs cannot clip it.
 */
import { LitElement, css, html, nothing, type TemplateResult } from "lit";
import { property } from "lit/decorators.js";
import { shared, tokens } from "./styles";

export interface ConfirmOptions {
  /** Bold first line, e.g. the task title. */
  title: string;
  /** The question, e.g. "Als erledigt markieren?". */
  text: string;
  /** Text of the confirm button. */
  confirm: string;
  cancel: string;
  /** Icon of the confirm button (e.g. mdi:check). */
  icon?: string;
  dark?: boolean;
}

export class LaeutwerkConfirm extends LitElement {
  @property({ attribute: false }) public options!: ConfirmOptions;
  public resolve?: (value: boolean) => void;
  private _onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      this._answer(false);
    }
  };

  public connectedCallback(): void {
    super.connectedCallback();
    // Capture: Escape closes this popup, not the dialog below it.
    document.addEventListener("keydown", this._onKey, true);
  }

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    document.removeEventListener("keydown", this._onKey, true);
  }

  protected firstUpdated(): void {
    this.renderRoot.querySelector<HTMLButtonElement>(".primary")?.focus();
  }

  private _answer(value: boolean): void {
    this.resolve?.(value);
    this.remove();
  }

  protected render(): TemplateResult {
    const o = this.options;
    return html`<div class="backdrop" @click=${() => this._answer(false)}></div>
      <div class="box" role="alertdialog" aria-modal="true" aria-label=${o.text}>
        <div class="title">${o.title}</div>
        <div class="text">${o.text}</div>
        <div class="actions">
          <button class="pill outline" @click=${() => this._answer(false)}>${o.cancel}</button>
          <button class="pill primary" @click=${() => this._answer(true)}>
            ${o.icon ? html`<ha-icon .icon=${o.icon}></ha-icon>` : nothing}${o.confirm}
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
        box-sizing: border-box;
        padding: 18px;
        border-radius: var(--lw-radius-card);
        background: var(--lw-bg);
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .title {
        font-size: 17px;
        font-weight: 700;
      }
      .text {
        font-size: 15px;
        color: var(--lw-text-2);
      }
      .actions {
        margin-top: 6px;
      }
    `,
  ];
}

/** Ask before an action; resolves true when confirmed. */
export function confirmAction(options: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    const popup = document.createElement("laeutwerk-confirm") as LaeutwerkConfirm;
    popup.options = options;
    popup.resolve = resolve;
    popup.toggleAttribute("dark", !!options.dark);
    document.body.appendChild(popup);
  });
}
