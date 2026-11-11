/**
 * One Home Assistant selector (entity, trigger, condition, action, icon,
 * object/YAML ...) with a plain fallback: `ha-selector` is lazy-loaded by
 * Home Assistant and may be missing (e.g. in the standalone preview).
 */
import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { property, state } from "lit/decorators.js";
import type { Localizer } from "./localize";
import { shared, tokens } from "./styles";
import type { HomeAssistant } from "./types";

declare global {
  interface Window {
    loadCardHelpers?: () => Promise<{
      createCardElement(config: Record<string, unknown>): HTMLElement;
    }>;
  }
}

let loading: Promise<boolean> | undefined;

/** Make sure `ha-selector` is defined (it is lazy-loaded by HA's card editors). */
export function ensureHaSelector(): Promise<boolean> {
  if (customElements.get("ha-selector")) return Promise.resolve(true);
  loading ??= (async () => {
    try {
      const helpers = await window.loadCardHelpers?.();
      const card = helpers?.createCardElement({ type: "tile", entity: "sun.sun" });
      const ctor = card?.constructor as { getConfigElement?: () => Promise<unknown> } | undefined;
      await ctor?.getConfigElement?.();
    } catch {
      // ignore – fallback below
    }
    await Promise.race([
      customElements.whenDefined("ha-selector"),
      new Promise((resolve) => setTimeout(resolve, 3000)),
    ]);
    return !!customElements.get("ha-selector");
  })();
  return loading;
}

/** Selector kinds whose fallback is a comma separated text field. */
const LIST_KINDS = ["entity"];
const TEXT_KINDS = ["icon", "text"];

export class LaeutwerkField extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @property({ attribute: false }) public localize!: Localizer;
  /** HA selector, e.g. `{ entity: { domain: "calendar", multiple: true } }`. */
  @property({ attribute: false }) public selector: Record<string, unknown> = {};
  @property({ attribute: false }) public value: unknown;
  @property() public label = "";
  /** Colour fields: colour offered by "choose a colour" (#rrggbb). */
  @property({ attribute: false }) public suggest = "";
  @state() private _native?: boolean;
  @state() private _text = "";
  @state() private _error?: string;

  public connectedCallback(): void {
    super.connectedCallback();
    if (this._native === undefined) void ensureHaSelector().then((ok) => (this._native = ok));
  }

  private get _kind(): string {
    return Object.keys(this.selector)[0] ?? "object";
  }

  protected willUpdate(changed: PropertyValues): void {
    if (changed.has("value") && !this._error) this._text = this._toText(this.value);
  }

  private _toText(value: unknown): string {
    if (LIST_KINDS.includes(this._kind)) {
      return Array.isArray(value) ? value.join(", ") : String(value ?? "");
    }
    if (TEXT_KINDS.includes(this._kind)) return String(value ?? "");
    return value === undefined || value === null ? "" : JSON.stringify(value, null, 2);
  }

  private _emit(value: unknown): void {
    // The parent stores the value and passes it back (one-way data flow).
    this.dispatchEvent(new CustomEvent("value-changed", { detail: { value } }));
  }

  /**
   * Colour: the value is "#rrggbb" for Läutwerk, HA's colour selector works
   * with [r, g, b]; without HA's elements a plain colour input.
   */
  private _renderColor() {
    const hex = typeof this.value === "string" && this.value ? this.value : "";
    if (!hex) {
      // An empty picker would show black: offer "choose a colour" instead.
      const label = this.label || this.localize.t("pick_color");
      return html`<button
        class="chip dashed pick"
        aria-label=${label}
        title=${label}
        @click=${() => this._emit(this.suggest || "#8a8a94")}
      >
        <ha-icon icon="mdi:palette-outline"></ha-icon
        >${this.label ? html`<span>${this.label}</span>` : nothing}
      </button>`;
    }
    return html`<div class="colorrow">
      ${this._colorPicker(hex)}
      <button
        class="mini"
        aria-label=${this.localize.t("no_color")}
        title=${this.localize.t("no_color")}
        @click=${() => this._emit("")}
      >
        <ha-icon icon="mdi:close"></ha-icon>
      </button>
    </div>`;
  }

  private _colorPicker(hex: string) {
    if (this._native && this.hass) {
      return html`<ha-selector
        .hass=${this.hass}
        .selector=${this.selector}
        .value=${hexToRgb(hex)}
        .label=${this.label}
        .required=${false}
        @value-changed=${(ev: CustomEvent<{ value: number[] | undefined }>) => {
          ev.stopPropagation();
          const rgb = ev.detail.value;
          this._emit(Array.isArray(rgb) && rgb.length === 3 ? rgbToHex(rgb) : "");
        }}
      ></ha-selector>`;
    }
    return html`<label class="field">
      <span>${this.label}</span>
      <input
        type="color"
        class="color"
        .value=${hex}
        @change=${(ev: Event) => this._emit((ev.target as HTMLInputElement).value)}
      />
    </label>`;
  }

  private _onSelector(ev: CustomEvent<{ value: unknown }>): void {
    ev.stopPropagation();
    this._emit(ev.detail.value);
  }

  private _onText(ev: Event): void {
    this._text = (ev.target as HTMLInputElement | HTMLTextAreaElement).value;
    const kind = this._kind;
    if (LIST_KINDS.includes(kind)) {
      const list = this._text
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const multiple = (this.selector[kind] as { multiple?: boolean } | undefined)?.multiple;
      this._emit(multiple ? list : (list[0] ?? ""));
      return;
    }
    if (TEXT_KINDS.includes(kind)) {
      this._emit(this._text);
      return;
    }
    try {
      const parsed: unknown = this._text.trim() ? JSON.parse(this._text) : undefined;
      this._error = undefined;
      this._emit(parsed);
    } catch (err) {
      this._error = err instanceof Error ? err.message : String(err);
    }
  }

  protected render() {
    if (this._native === undefined) return html`<div class="hint">…</div>`;
    if (this._kind === "color_rgb") return this._renderColor();
    if (this._native && this.hass) {
      return html`<ha-selector
        .hass=${this.hass}
        .selector=${this.selector}
        .value=${this.value}
        .label=${this.label}
        .required=${false}
        @value-changed=${this._onSelector}
      ></ha-selector>`;
    }
    const simple = LIST_KINDS.includes(this._kind) || TEXT_KINDS.includes(this._kind);
    return html`<label class="field">
      <span>${this.label}${simple ? nothing : html` (${this.localize.t("json_hint")})`}</span>
      ${
        simple
          ? html`<input .value=${this._text} @input=${this._onText} />`
          : html`<textarea
              spellcheck="false"
              .value=${this._text}
              @input=${this._onText}
            ></textarea>`
      }
      ${
        this._error
          ? html`<span class="err"
              >${this.localize.t("invalid_json", { error: this._error })}</span
            >`
          : nothing
      }
    </label>`;
  }

  static styles = [
    tokens,
    shared,
    css`
      :host {
        display: block;
        min-width: 0;
      }
      textarea {
        min-height: 120px;
        font-family: ui-monospace, monospace;
        font-size: 12px;
      }
      .colorrow {
        display: flex;
        align-items: center;
        gap: 2px;
      }
      .colorrow > :first-child {
        flex: 1;
        min-width: 0;
      }
      .pick {
        min-height: 40px;
      }
      input.color {
        width: 64px;
        padding: 4px;
      }
      .err {
        color: var(--lw-danger);
      }
    `,
  ];
}

export function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function rgbToHex(rgb: number[]): string {
  return `#${rgb
    .map((v) =>
      Math.max(0, Math.min(255, Math.round(v)))
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")}`;
}
