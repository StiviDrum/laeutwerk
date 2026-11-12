/**
 * Text input with a dropdown of suggestions while typing.
 * - `variables`: typing `{` (+ letters) offers these names, picking one
 *   inserts `{name}` at the cursor.
 * - `items`: otherwise the whole text is matched against the items (e.g.
 *   known NFC tags); picking one replaces the text.
 * The list is `position: fixed`, so scroll containers do not clip it.
 */
import { LitElement, css, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import { filterSuggestions, insertVariable, variableQuery } from "./format";
import { shared, tokens } from "./styles";

export interface SuggestItem {
  value: string;
  /** Shown name (e.g. tag name); the value is shown small beside it. */
  label?: string;
}

export class LaeutwerkSuggest extends LitElement {
  @property() public value = "";
  @property() public label = "";
  @property() public placeholder = "";
  @property({ type: Boolean }) public multiline = false;
  @property({ attribute: false }) public variables: string[] = [];
  @property({ attribute: false }) public items: SuggestItem[] = [];
  @state() private _shown: SuggestItem[] = [];
  @state() private _variableMode = false;
  @state() private _index = 0;
  @state() private _pos?: { left: number; width: number; top?: number; bottom?: number };
  private _query: { start: number; query: string } | null = null;

  private get _input(): HTMLInputElement | HTMLTextAreaElement | null {
    return this.renderRoot.querySelector("input, textarea");
  }

  public connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("scroll", this._reposition, true);
    window.addEventListener("resize", this._reposition);
  }

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    window.removeEventListener("scroll", this._reposition, true);
    window.removeEventListener("resize", this._reposition);
  }

  protected updated(changed: PropertyValues): void {
    // Items may arrive late (tags are loaded asynchronously).
    if (changed.has("items") || (changed.has("variables") && this._shown.length)) this._refresh();
  }

  private _reposition = (): void => {
    if (!this._shown.length) return;
    const input = this._input;
    if (!input) return;
    const rect = input.getBoundingClientRect();
    const below = window.innerHeight - rect.bottom;
    this._pos = {
      left: rect.left,
      width: rect.width,
      ...(below < 190 && rect.top > below
        ? { bottom: window.innerHeight - rect.top + 2 }
        : { top: rect.bottom + 2 }),
    };
  };

  /** Recompute the suggestions for the current text and cursor. */
  private _refresh(): void {
    const input = this._input;
    if (!input) return;
    const text = input.value;
    let list: SuggestItem[] = [];
    this._query = this.variables.length
      ? variableQuery(text, input.selectionStart ?? text.length)
      : null;
    this._variableMode = !!this._query;
    if (this._query) {
      list = filterSuggestions(
        this.variables.map((value) => ({ value })),
        this._query.query,
      );
    } else if (this.items.length) {
      list = filterSuggestions(this.items, text);
      // Nothing left to suggest once the text is exactly one item.
      if (list.length === 1 && list[0].value === text) list = [];
    }
    this._shown = list;
    this._index = Math.min(this._index, Math.max(list.length - 1, 0));
    this._reposition();
  }

  private _close(): void {
    this._shown = [];
  }

  private _emit(value: string): void {
    this.dispatchEvent(new CustomEvent("value-changed", { detail: { value } }));
  }

  private _onInput(e: Event): void {
    const input = e.target as HTMLInputElement | HTMLTextAreaElement;
    this._index = 0;
    this._emit(input.value);
    this._refresh();
  }

  private _pick(item: SuggestItem): void {
    const input = this._input;
    if (!input) return;
    if (this._variableMode) {
      const result = insertVariable(
        input.value,
        input.selectionStart ?? input.value.length,
        item.value,
      );
      if (!result) return;
      input.value = result.text;
      input.setSelectionRange(result.cursor, result.cursor);
      this._emit(result.text);
    } else {
      input.value = item.value;
      this._emit(item.value);
    }
    this._close();
    input.focus();
    this.dispatchEvent(new CustomEvent("change"));
  }

  private _onKey(e: KeyboardEvent): void {
    if (e.key === "Escape" && this._shown.length) {
      e.stopPropagation();
      this._close();
      return;
    }
    if (!this._shown.length) {
      // Cursor moves can start or end a `{query`.
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") queueMicrotask(() => this._refresh());
      return;
    }
    const n = this._shown.length;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      this._index = (this._index + (e.key === "ArrowDown" ? 1 : n - 1)) % n;
    } else if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      this._pick(this._shown[this._index]);
    }
  }

  private _onBlur(): void {
    this._close();
    this.dispatchEvent(new CustomEvent("change"));
  }

  private _item(item: SuggestItem, i: number): TemplateResult {
    const variables = this._variableMode;
    return html`<li
      role="option"
      aria-selected=${i === this._index}
      class=${i === this._index ? "sel" : ""}
      @mousedown=${(e: Event) => e.preventDefault()}
      @click=${() => this._pick(item)}
    >
      ${
        variables
          ? html`<span class="var">{${item.value}}</span>`
          : html`<span>${item.label || item.value}</span>${
                item.label && item.label !== item.value
                  ? html`<span class="id">${item.value}</span>`
                  : nothing
              }`
      }
    </li>`;
  }

  protected render(): TemplateResult {
    const common = {
      role: "combobox",
      expanded: String(this._shown.length > 0),
    };
    const input = this.multiline
      ? html`<textarea
          role=${common.role}
          aria-expanded=${common.expanded}
          aria-autocomplete="list"
          .value=${this.value ?? ""}
          placeholder=${this.placeholder}
          @input=${this._onInput}
          @keydown=${this._onKey}
          @focus=${() => this._refresh()}
          @click=${() => this._refresh()}
          @blur=${this._onBlur}
        ></textarea>`
      : html`<input
          role=${common.role}
          aria-expanded=${common.expanded}
          aria-autocomplete="list"
          autocomplete="off"
          .value=${this.value ?? ""}
          placeholder=${this.placeholder}
          @input=${this._onInput}
          @keydown=${this._onKey}
          @focus=${() => this._refresh()}
          @click=${() => this._refresh()}
          @blur=${this._onBlur}
        />`;
    const pos = this._pos;
    return html`<label class="field"
        >${this.label ? html`<span>${this.label}</span>` : nothing} ${input}</label
      >
      ${
        this._shown.length && pos
          ? html`<ul
              class="list"
              role="listbox"
              style="left:${pos.left}px;width:${pos.width}px;${
                pos.top !== undefined ? `top:${pos.top}px` : `bottom:${pos.bottom}px`
              }"
            >
              ${this._shown.map((item, i) => this._item(item, i))}
            </ul>`
          : nothing
      }`;
  }

  static styles = [
    tokens,
    shared,
    css`
      :host {
        display: block;
      }
      .list {
        position: fixed;
        z-index: 1002;
        margin: 0;
        padding: 4px;
        list-style: none;
        box-sizing: border-box;
        max-height: 220px;
        overflow-y: auto;
        border-radius: 16px;
        border: 1px solid var(--lw-border);
        background: var(--lw-bg);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
      }
      li {
        display: flex;
        align-items: baseline;
        gap: 8px;
        min-height: 44px;
        box-sizing: border-box;
        padding: 0 12px;
        border-radius: 12px;
        align-items: center;
        font-size: 14px;
        cursor: pointer;
      }
      li.sel {
        background: color-mix(in srgb, var(--lw-accent) 16%, transparent);
      }
      .var {
        font-family: ui-monospace, monospace;
      }
      .id {
        font-size: 12px;
        color: var(--lw-text-2);
        font-family: ui-monospace, monospace;
        overflow: hidden;
        text-overflow: ellipsis;
      }
    `,
  ];
}
