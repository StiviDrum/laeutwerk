/**
 * Own colour picker (hue/saturation wheel + favourites + hex input) in a popup
 * on <body>. No dependency on Home Assistant's internal colour elements.
 */
import { overlayHost } from "./overlay-host";
import { LitElement, css, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import { shared, tokens } from "./styles";

/** Normalise "#abc", "abc", "#AABBCC" to "#aabbcc"; null when invalid. */
export function normalizeHex(input: string): string | null {
  let s = String(input ?? "")
    .trim()
    .replace(/^#/, "")
    .toLowerCase();
  if (/^[0-9a-f]{3}$/.test(s)) s = [...s].map((c) => c + c).join("");
  return /^[0-9a-f]{6}$/.test(s) ? `#${s}` : null;
}

/** "#rrggbb" -> hue 0..360, saturation 0..1 (value is ignored). */
export function hexToHs(hex: string): { h: number; s: number } {
  const n = normalizeHex(hex) ?? "#ffffff";
  const r = parseInt(n.slice(1, 3), 16) / 255;
  const g = parseInt(n.slice(3, 5), 16) / 255;
  const b = parseInt(n.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const d = max - min;
  let h = 0;
  if (d > 0) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
  }
  return { h, s: max === 0 ? 0 : d / max };
}

/** Hue 0..360, saturation 0..1 (value 1) -> "#rrggbb". */
export function hsToHex(h: number, s: number): string {
  const hh = ((h % 360) + 360) % 360;
  const sat = Math.max(0, Math.min(1, s));
  const c = sat;
  const x = c * (1 - Math.abs(((hh / 60) % 2) - 1));
  const m = 1 - c;
  const sector = Math.floor(hh / 60) % 6;
  const [r, g, b] = [
    [c, x, 0],
    [x, c, 0],
    [0, c, x],
    [0, x, c],
    [x, 0, c],
    [c, 0, x],
  ][sector]!;
  return `#${[r, g, b]
    .map((v) =>
      Math.round((v + m) * 255)
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")}`;
}

/** Wheel position (x, y in -1..1, centre 0,0, y down) for hue/saturation. */
export function hsToXy(h: number, s: number): { x: number; y: number } {
  const a = (h * Math.PI) / 180;
  const r = Math.max(0, Math.min(1, s));
  return { x: r * Math.cos(a), y: r * Math.sin(a) };
}

/** Wheel position -> hue/saturation; points outside the circle are clamped to the edge. */
export function xyToHs(x: number, y: number): { h: number; s: number } {
  const r = Math.min(1, Math.hypot(x, y));
  let h = (Math.atan2(y, x) * 180) / Math.PI;
  if (h < 0) h += 360;
  return { h: r === 0 ? 0 : h, s: r };
}

export const FAVORITES = [
  "#ffd6a5",
  "#ffffff",
  "#ff3b30",
  "#ff9500",
  "#ffcc00",
  "#34c759",
  "#32d4d4",
  "#2f6bff",
  "#af52de",
  "#ff4f8b",
  "#8a8a94",
];

export interface ColorPickOptions {
  title: string;
  value: string;
  swatches?: { label: string; color: string }[];
  allowClear?: boolean;
  dark?: boolean;
  /** Localised strings. */
  labels: {
    favorites: string;
    keywordColors: string;
    cancel: string;
    apply: string;
    remove: string;
    hexInvalid: string;
    wheel: string;
  };
}

const SIZE = 240;

export class LaeutwerkColorPopup extends LitElement {
  @property({ attribute: false }) public options!: ColorPickOptions;
  public resolve?: (value: string | null) => void;
  @state() private _hex = "#ffffff";
  @state() private _h = 0;
  @state() private _s = 0;
  @state() private _text = "";
  @state() private _invalid = false;
  private _drawn = 0;

  private _onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      this._answer(null);
    }
  };

  public connectedCallback(): void {
    super.connectedCallback();
    document.addEventListener("keydown", this._onKey, true);
  }

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    document.removeEventListener("keydown", this._onKey, true);
  }

  protected willUpdate(changed: PropertyValues): void {
    if (changed.has("options") && this.options) {
      const hex = normalizeHex(this.options.value) ?? "#ffffff";
      this._setFromHex(hex);
    }
  }

  protected firstUpdated(): void {
    this._draw();
    this.renderRoot.querySelector<HTMLElement>(".marker")?.focus();
  }

  private _setFromHex(hex: string): void {
    const { h, s } = hexToHs(hex);
    this._hex = hex;
    this._h = h;
    this._s = s;
    this._text = hex;
    this._invalid = false;
  }

  /** Move the marker; this always yields a value-1 colour. */
  private _setHs(h: number, s: number): void {
    this._h = ((h % 360) + 360) % 360;
    this._s = Math.max(0, Math.min(1, s));
    this._hex = hsToHex(this._h, this._s);
    this._text = this._hex;
    this._invalid = false;
  }

  private _answer(value: string | null): void {
    this.resolve?.(value);
    this.remove();
  }

  private _draw(): void {
    const canvas = this.renderRoot.querySelector<HTMLCanvasElement>("canvas");
    if (!canvas) return;
    const dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
    if (this._drawn === dpr) return;
    this._drawn = dpr;
    const px = Math.round(SIZE * dpr);
    canvas.width = px;
    canvas.height = px;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const c = px / 2;
    const hues = ctx.createConicGradient(0, c, c);
    // Angle 0 = pointing right, clockwise: matches the polar mapping (hue 0 at the right).
    for (let i = 0; i <= 12; i++) hues.addColorStop(i / 12, `hsl(${i * 30}deg 100% 50%)`);
    ctx.fillStyle = hues;
    ctx.fillRect(0, 0, px, px);
    const white = ctx.createRadialGradient(c, c, 0, c, c, c);
    white.addColorStop(0, "rgba(255,255,255,1)");
    white.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = white;
    ctx.fillRect(0, 0, px, px);
  }

  private _fromPointer(e: PointerEvent): void {
    const wheel = this.renderRoot.querySelector<HTMLElement>(".wheel")!;
    const r = wheel.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * 2 - 1;
    const y = ((e.clientY - r.top) / r.height) * 2 - 1;
    const { h, s } = xyToHs(x, y);
    this._setHs(h, s);
  }

  private _down = (e: PointerEvent): void => {
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    this._fromPointer(e);
  };

  private _move = (e: PointerEvent): void => {
    if ((e.currentTarget as HTMLElement).hasPointerCapture(e.pointerId)) this._fromPointer(e);
  };

  private _wheelKey = (e: KeyboardEvent): void => {
    const step: Record<string, [number, number]> = {
      ArrowLeft: [-5, 0],
      ArrowRight: [5, 0],
      ArrowUp: [0, 0.05],
      ArrowDown: [0, -0.05],
    };
    const d = step[e.key];
    if (!d) return;
    e.preventDefault();
    this._setHs(this._h + d[0], this._s + d[1]);
  };

  private _onHex(e: Event): void {
    this._text = (e.target as HTMLInputElement).value;
    const hex = normalizeHex(this._text);
    this._invalid = !hex;
    if (hex) {
      const { h, s } = hexToHs(hex);
      this._hex = hex;
      this._h = h;
      this._s = s;
    }
  }

  private _apply(): void {
    const hex = normalizeHex(this._text);
    if (hex) this._answer(hex);
    else this._invalid = true;
  }

  private _swatch(color: string, label: string): TemplateResult {
    const n = normalizeHex(color) ?? color;
    return html`<button
      class="sw"
      title=${label}
      aria-label=${label}
      aria-pressed=${n === this._hex}
      @click=${() => this._setFromHex(n)}
    >
      <span style="background:${n}"></span>
    </button>`;
  }

  protected render(): TemplateResult {
    const o = this.options;
    const l = o.labels;
    const { x, y } = hsToXy(this._h, this._s);
    const pos = `left:${((x + 1) / 2) * 100}%;top:${((y + 1) / 2) * 100}%`;
    const swatches = (o.swatches ?? []).filter((s) => normalizeHex(s.color));
    return html`<div class="backdrop" @click=${() => this._answer(null)}></div>
      <div class="box" role="dialog" aria-modal="true" aria-label=${o.title}>
        <div class="title">${o.title}</div>
        <div class="wheel" @pointerdown=${this._down} @pointermove=${this._move}>
          <canvas></canvas>
          <div
            class="marker"
            tabindex="0"
            role="slider"
            aria-label=${`${l.wheel} ${this._hex}`}
            aria-valuetext=${this._hex}
            style="${pos};background:${this._hex}"
            @keydown=${this._wheelKey}
          ></div>
        </div>
        <div class="sublabel">${l.favorites}</div>
        <div class="swrow">${FAVORITES.map((c) => this._swatch(c, c))}</div>
        ${
          swatches.length
            ? html`<div class="sublabel">${l.keywordColors}</div>
                <div class="swrow">${swatches.map((s) => this._swatch(s.color, s.label))}</div>`
            : nothing
        }
        <div class="hexrow">
          <span class="preview" style="background:${this._hex}"></span>
          <input
            class=${this._invalid ? "invalid" : ""}
            .value=${this._text}
            maxlength="7"
            spellcheck="false"
            autocomplete="off"
            aria-label="Hex"
            aria-invalid=${this._invalid}
            @input=${this._onHex}
            @keydown=${(e: KeyboardEvent) => e.key === "Enter" && this._apply()}
          />
        </div>
        ${this._invalid ? html`<div class="err">${l.hexInvalid}</div>` : nothing}
        <div class="actions">
          <button class="pill outline" @click=${() => this._answer(null)}>${l.cancel}</button>
          <button class="pill primary" @click=${this._apply}>${l.apply}</button>
        </div>
        ${
          o.allowClear
            ? html`<button class="clear" @click=${() => this._answer("")}>
                <ha-icon icon="mdi:close"></ha-icon>${l.remove}
              </button>`
            : nothing
        }
      </div>`;
  }

  protected updated(): void {
    this._draw();
  }

  static styles = [
    tokens,
    shared,
    css`
      :host {
        position: fixed;
        inset: 0;
        z-index: 1002;
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
        gap: 10px;
      }
      .title {
        font-size: 17px;
        font-weight: 700;
      }
      .sublabel {
        font-size: 12px;
        font-weight: 600;
        color: var(--lw-text-2);
        margin-top: 4px;
      }
      .wheel {
        position: relative;
        align-self: center;
        width: min(240px, 70vw);
        aspect-ratio: 1;
        border-radius: 50%;
        touch-action: none;
        cursor: crosshair;
        flex: none;
      }
      canvas {
        width: 100%;
        height: 100%;
        border-radius: 50%;
        display: block;
      }
      .marker {
        position: absolute;
        width: 28px;
        height: 28px;
        box-sizing: border-box;
        margin: -14px 0 0 -14px;
        border-radius: 50%;
        border: 3px solid #fff;
        box-shadow: 0 1px 5px rgba(0, 0, 0, 0.5);
        outline: none;
      }
      .marker:focus-visible {
        outline: 2px solid var(--lw-accent);
        outline-offset: 3px;
      }
      .swrow {
        display: flex;
        flex-wrap: wrap;
      }
      .sw {
        width: 44px;
        height: 44px;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .sw span {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        box-sizing: border-box;
        border: 1px solid var(--lw-border);
      }
      .sw[aria-pressed="true"] span {
        outline: 2px solid var(--lw-accent);
        outline-offset: 2px;
      }
      .hexrow {
        display: flex;
        align-items: center;
        gap: 12px;
      }
      .preview {
        width: 48px;
        height: 48px;
        flex: none;
        border-radius: 50%;
        border: 1px solid var(--lw-border);
      }
      .hexrow input {
        flex: 1;
        min-width: 0;
        min-height: 44px;
        padding: 0 14px;
        box-sizing: border-box;
        border-radius: 22px;
        border: 1px solid var(--lw-border);
        background: var(--lw-surface);
        color: var(--lw-text);
        font: inherit;
        font-family: ui-monospace, monospace;
      }
      .hexrow input.invalid {
        border-color: var(--lw-danger);
        color: var(--lw-danger);
      }
      .err {
        font-size: 12px;
        color: var(--lw-danger);
      }
      .clear {
        min-height: 44px;
        align-self: center;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 13px;
        color: var(--lw-text-2);
      }
      .clear ha-icon {
        --mdc-icon-size: 16px;
      }
    `,
  ];
}

/** Open the picker; resolves "#rrggbb", "" (removed) or null (cancelled). */
export function pickColor(options: ColorPickOptions): Promise<string | null> {
  return new Promise((resolve) => {
    const popup = document.createElement("laeutwerk-color-popup") as LaeutwerkColorPopup;
    popup.options = options;
    popup.resolve = resolve;
    popup.toggleAttribute("dark", !!options.dark);
    overlayHost().appendChild(popup);
  });
}
