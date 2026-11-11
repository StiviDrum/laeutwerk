/**
 * "Neue Regel": choose a built-in or own template, an empty rule, or import
 * rules as YAML (assistant for new rules, SPEC B7).
 */
import { LitElement, css, html, nothing, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import { emptyRule, ruleFromTemplate } from "./format";
import type { Localizer } from "./localize";
import { shared, tokens } from "./styles";
import type { HomeAssistant, Rule, RuleTemplate } from "./types";

function errorText(err: unknown): string {
  if (err && typeof err === "object" && "message" in err) return String(err.message);
  return String(err);
}

export class LaeutwerkTemplatePicker extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @property({ attribute: false }) public localize!: Localizer;
  @state() private _templates?: RuleTemplate[];
  @state() private _error?: string;
  @state() private _import = false;
  @state() private _yaml = "";
  @state() private _busy = false;

  public connectedCallback(): void {
    super.connectedCallback();
    void this._load();
  }

  private async _load(): Promise<void> {
    if (!this.hass) return;
    try {
      const res = await this.hass.callWS<{ templates: RuleTemplate[] }>({
        type: "laeutwerk/templates/list",
      });
      this._templates = res.templates;
    } catch (err) {
      this._templates = [];
      this._error = errorText(err);
    }
  }

  private _pick(rule: Rule): void {
    this.dispatchEvent(new CustomEvent("pick", { detail: { rule } }));
  }

  private async _deleteTemplate(template: RuleTemplate): Promise<void> {
    if (!this.hass) return;
    try {
      await this.hass.callWS({ type: "laeutwerk/templates/delete", template_id: template.id });
      await this._load();
    } catch (err) {
      this._error = errorText(err);
    }
  }

  private async _doImport(): Promise<void> {
    if (!this.hass || !this._yaml.trim()) return;
    this._busy = true;
    this._error = undefined;
    try {
      await this.hass.callWS({ type: "laeutwerk/rules/import", yaml: this._yaml });
      this.dispatchEvent(new CustomEvent("imported"));
    } catch (err) {
      this._error = this.localize.t("failed", { error: errorText(err) });
    } finally {
      this._busy = false;
    }
  }

  protected render(): TemplateResult {
    const l = this.localize;
    return html`<div class="page">
      <div class="separator">${l.t("templates_title")}<span class="line"></span></div>
      <div class="hint">${l.t("templates_hint")}</div>
      <div class="list">
        <button class="tpl" @click=${() => this._pick(emptyRule())}>
          <span class="icon small"><ha-icon icon="mdi:plus"></ha-icon></span>
          <span class="grow text">
            <span class="name">${l.t("template_empty")}</span>
            <span class="sub">${l.t("template_empty_hint")}</span>
          </span>
        </button>
        ${
          this._templates === undefined
            ? html`<div class="hint">${l.t("loading")}</div>`
            : this._templates.map(
                (t) =>
                  html`<div class="row">
                    <button class="tpl grow" @click=${() => this._pick(ruleFromTemplate(t))}>
                      <span
                        class="icon small"
                        style=${
                          t.rule.color
                            ? `background: color-mix(in srgb, ${t.rule.color} 22%, transparent); color: ${t.rule.color}`
                            : ""
                        }
                      >
                        <ha-icon .icon=${t.rule.icon || "mdi:bell-ring-outline"}></ha-icon>
                      </span>
                      <span class="grow text">
                        <span class="name">${t.name}</span>
                        <span class="sub"
                          >${t.description || (t.builtin ? "" : l.t("template_own"))}</span
                        >
                      </span>
                    </button>
                    ${
                      t.builtin
                        ? nothing
                        : html`<button
                            class="mini"
                            aria-label=${l.t("delete_template")}
                            @click=${() => this._deleteTemplate(t)}
                          >
                            <ha-icon icon="mdi:delete-outline"></ha-icon>
                          </button>`
                    }
                  </div>`,
              )
        }
      </div>
      ${
        this._import
          ? html`<div class="panel">
              <div class="step">${l.t("import_yaml")}</div>
              <div class="hint">${l.t("import_hint")}</div>
              <textarea
                class="yaml"
                spellcheck="false"
                .value=${this._yaml}
                @input=${(e: Event) => (this._yaml = (e.target as HTMLTextAreaElement).value)}
              ></textarea>
              <button
                class="pill primary"
                ?disabled=${this._busy || !this._yaml.trim()}
                @click=${this._doImport}
              >
                ${l.t("import_button")}
              </button>
            </div>`
          : html`<div class="wrap">
              <button class="chip dashed" @click=${() => (this._import = true)}>
                <ha-icon icon="mdi:import"></ha-icon>${l.t("import_yaml")}
              </button>
            </div>`
      }
      ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
      <div class="actions">
        <button class="pill outline" @click=${() => this.dispatchEvent(new CustomEvent("cancel"))}>
          ${l.t("cancel")}
        </button>
      </div>
    </div>`;
  }

  static styles = [
    tokens,
    shared,
    css`
      .page {
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      .tpl {
        display: flex;
        align-items: center;
        gap: 10px;
        min-height: 56px;
        padding: 6px 10px;
        border-radius: 18px;
        background: var(--lw-surface);
        text-align: left;
        width: 100%;
      }
      .text {
        display: flex;
        flex-direction: column;
        gap: 2px;
        min-width: 0;
      }
      .sub {
        white-space: normal;
      }
      .yaml {
        min-height: 160px;
        font-family: ui-monospace, monospace;
        font-size: 12px;
      }
    `,
  ];
}
