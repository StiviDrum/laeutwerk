/**
 * "Neue Regel": choose a built-in or own template, an empty rule, or import
 * rules as YAML (assistant for new rules, SPEC B7).
 */
import { LitElement, css, html, nothing, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import { ruleFromTemplate } from "./format";
import { applyNeeds, askedNeeds, type TemplateNeed } from "./rule-build";
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
  /** "templates" = built-in and own templates, "import" = paste YAML. */
  @property() public mode: "templates" | "import" = "templates";
  @state() private _templates?: RuleTemplate[];
  /** Template waiting for the entities it needs. */
  @state() private _asking?: { rule: Rule; needs: TemplateNeed[] };
  @state() private _answers: Record<string, string> = {};
  @state() private _error?: string;
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

  private _choose(t: RuleTemplate): void {
    const needs: TemplateNeed[] = t.needs ?? [];
    const rule = ruleFromTemplate(t);
    if (!askedNeeds(needs).length) return this._pick(applyNeeds(rule, needs, {}));
    this._answers = {};
    this._asking = { rule, needs };
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

  private _renderNeeds(): TemplateResult {
    const l = this.localize;
    const { rule, needs } = this._asking!;
    const asked = askedNeeds(needs);
    return html`<div class="page">
      <div class="separator">${l.t("tpl_needs_title")}<span class="line"></span></div>
      <div class="hint">${l.t("tpl_needs_hint")}</div>
      ${asked.map(
        (n) =>
          html`<laeutwerk-field
            .hass=${this.hass}
            .localize=${l}
            .label=${n.label}
            .selector=${{ entity: { domain: n.domain } }}
            .value=${this._answers[n.path] ?? ""}
            @value-changed=${(e: CustomEvent<{ value: unknown }>) =>
              (this._answers = { ...this._answers, [n.path]: String(e.detail.value ?? "") })}
          ></laeutwerk-field>`,
      )}
      <div class="actions">
        <button class="pill outline" @click=${() => (this._asking = undefined)}>
          ${l.t("back")}
        </button>
        <button
          class="pill primary"
          ?disabled=${asked.some((n) => !this._answers[n.path])}
          @click=${() => this._pick(applyNeeds(rule, needs, this._answers))}
        >
          ${l.t("tpl_continue")}
        </button>
      </div>
    </div>`;
  }

  private _renderImport(): TemplateResult {
    const l = this.localize;
    return html`<div class="page">
      <div class="separator">${l.t("import_yaml")}<span class="line"></span></div>
      <div class="hint">${l.t("import_hint")}</div>
      <textarea
        class="yaml"
        spellcheck="false"
        .value=${this._yaml}
        @input=${(e: Event) => (this._yaml = (e.target as HTMLTextAreaElement).value)}
      ></textarea>
      ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
      <div class="actions">
        <button class="pill outline" @click=${() => this.dispatchEvent(new CustomEvent("cancel"))}>
          ${l.t("back")}
        </button>
        <button
          class="pill primary"
          ?disabled=${this._busy || !this._yaml.trim()}
          @click=${this._doImport}
        >
          ${l.t("import_button")}
        </button>
      </div>
    </div>`;
  }

  protected render(): TemplateResult {
    const l = this.localize;
    if (this.mode === "import") return this._renderImport();
    if (this._asking) return this._renderNeeds();
    return html`<div class="page">
      <div class="separator">${l.t("new_template")}<span class="line"></span></div>
      <div class="hint">${l.t("templates_hint")}</div>
      <div class="list">
        ${
          this._templates === undefined
            ? html`<div class="hint">${l.t("loading")}</div>`
            : this._templates.map(
                (t) =>
                  html`<div class="row">
                    <button class="tpl grow" @click=${() => this._choose(t)}>
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
      ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
      <div class="actions">
        <button class="pill outline" @click=${() => this.dispatchEvent(new CustomEvent("cancel"))}>
          ${l.t("back")}
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
