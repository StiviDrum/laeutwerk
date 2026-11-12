/** Visual editor for the card configuration (getConfigElement). */
import { LitElement, css, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";
import { ensureHaSelector } from "./ha-field";
import { helpTip } from "./help-tip";
import { localizer, type StringKey } from "./localize";
import type { HomeAssistant, LaeutwerkCardConfig, Rule } from "./types";

type Schema = { name: keyof LaeutwerkCardConfig; selector: Record<string, unknown> }[];

const LABELS: Record<string, StringKey> = {
  view: "ed_view",
  rule: "ed_rule",
  rules: "ed_rules",
  show_upcoming: "ed_show_upcoming",
  show_done: "ed_show_done",
  compact: "ed_compact",
};

/** Drop empty values and the keys that do not belong to the chosen view. */
export function cleanCardConfig(config: LaeutwerkCardConfig): LaeutwerkCardConfig {
  const clean: Record<string, unknown> = { ...config };
  for (const [key, value] of Object.entries(clean)) {
    if (value === "" || value === undefined || (Array.isArray(value) && !value.length)) {
      delete clean[key];
    }
  }
  if (clean.view === "rule") delete clean.rules;
  else delete clean.rule;
  clean.type = config.type ?? "custom:laeutwerk-card";
  return clean as unknown as LaeutwerkCardConfig;
}

export class LaeutwerkCardEditor extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @state() private _config?: LaeutwerkCardConfig;
  @state() private _rules?: Rule[];
  @state() private _native = false;
  private _loading = false;

  public setConfig(config: LaeutwerkCardConfig): void {
    this._config = config;
  }

  public connectedCallback(): void {
    super.connectedCallback();
    void ensureHaSelector().then(() => (this._native = !!customElements.get("ha-form")));
  }

  protected willUpdate(): void {
    if (this.hass && this._rules === undefined && !this._loading) {
      this._loading = true;
      this.hass
        .callWS<{ rules: Rule[] }>({ type: "laeutwerk/rules/list" })
        .then((r) => (this._rules = r.rules))
        .catch(() => (this._rules = []));
    }
  }

  private get _l() {
    return localizer(this.hass?.locale?.language ?? this.hass?.language);
  }

  private _schema(view: string): Schema {
    const l = this._l;
    const options = (this._rules ?? []).map((r) => ({ value: r.id ?? "", label: r.name }));
    const schema: Schema = [
      {
        name: "view",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "overview", label: l.t("ed_view_overview") },
              { value: "rule", label: l.t("ed_view_rule") },
            ],
          },
        },
      },
    ];
    if (view === "rule") {
      schema.push({
        name: "rule",
        selector: { select: { mode: "dropdown", custom_value: true, options } },
      });
    } else {
      schema.push({
        name: "rules",
        selector: { select: { multiple: true, mode: "list", options } },
      });
    }
    schema.push(
      { name: "show_upcoming", selector: { boolean: {} } },
      { name: "show_done", selector: { boolean: {} } },
      { name: "compact", selector: { boolean: {} } },
    );
    return schema;
  }

  private _label = (field: { name: string }): string => {
    const key = LABELS[field.name];
    return key ? this._l.t(key) : field.name;
  };

  private _changed(config: LaeutwerkCardConfig): void {
    const clean = cleanCardConfig(config);
    this._config = clean;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: clean },
        bubbles: true,
        composed: true,
      }),
    );
  }

  protected render() {
    if (!this._config) return nothing;
    const data: LaeutwerkCardConfig = {
      view: "overview",
      show_upcoming: true,
      show_done: true,
      compact: false,
      ...this._config,
    };
    if (this._native && this.hass) {
      return html`<ha-form
          .hass=${this.hass}
          .data=${data}
          .schema=${this._schema(data.view ?? "overview")}
          .computeLabel=${this._label}
          @value-changed=${(ev: CustomEvent<{ value: LaeutwerkCardConfig }>) =>
            this._changed(ev.detail.value)}
        ></ha-form>
        <div class="helprow">${this._l.t("help")}${helpTip(this._l, "help_card_editor")}</div>`;
    }
    // Fallback without HA's form elements.
    const l = this._l;
    const set = (changes: Partial<LaeutwerkCardConfig>) =>
      this._changed({ ...this._config!, ...changes });
    const check = (key: "show_upcoming" | "show_done" | "compact") =>
      html`<label class="check"
        ><input
          type="checkbox"
          .checked=${!!data[key]}
          @change=${(ev: Event) => set({ [key]: (ev.target as HTMLInputElement).checked })}
        />${this._label({ name: key })}</label
      >`;
    return html`<div class="form">
      <label
        >${l.t("ed_view")}
        <select
          @change=${(ev: Event) =>
            set({ view: (ev.target as HTMLSelectElement).value as "overview" | "rule" })}
        >
          <option value="overview" ?selected=${data.view !== "rule"}>
            ${l.t("ed_view_overview")}
          </option>
          <option value="rule" ?selected=${data.view === "rule"}>${l.t("ed_view_rule")}</option>
        </select>
      </label>
      ${
        data.view === "rule"
          ? html`<label
              >${l.t("ed_rule")}
              <select
                @change=${(ev: Event) => set({ rule: (ev.target as HTMLSelectElement).value })}
              >
                <option value="" ?selected=${!data.rule}>–</option>
                ${(this._rules ?? []).map(
                  (r) =>
                    html`<option value=${r.id ?? ""} ?selected=${r.id === data.rule}>
                      ${r.name}
                    </option>`,
                )}
              </select>
            </label>`
          : html`<fieldset>
              <legend>${l.t("ed_rules")}</legend>
              ${(this._rules ?? []).map(
                (r) =>
                  html`<label class="check"
                    ><input
                      type="checkbox"
                      .checked=${(data.rules ?? []).includes(r.id ?? "")}
                      @change=${(ev: Event) => {
                        const on = (ev.target as HTMLInputElement).checked;
                        const current = (data.rules ?? []).filter((id) => id !== r.id);
                        set({ rules: on ? [...current, r.id ?? ""] : current });
                      }}
                    />${r.name}</label
                  >`,
              )}
            </fieldset>`
      }
      ${check("show_upcoming")} ${check("show_done")} ${check("compact")}
      <div class="helprow">${l.t("help")}${helpTip(l, "help_card_editor")}</div>
    </div>`;
  }

  static styles = css`
    .helprow {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 12px;
      color: var(--secondary-text-color);
    }
    .form {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    label {
      display: flex;
      flex-direction: column;
      gap: 4px;
      font-size: 13px;
    }
    fieldset {
      border: 0;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 4px;
      font-size: 13px;
    }
    label.check {
      flex-direction: row;
      align-items: center;
      gap: 8px;
    }
  `;
}
