/** "New rule": chooser (assistant, template, empty rule, import) and the two-question assistant. */
import { LitElement, css, html, nothing, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import { emptyRule } from "./format";
import type { Localizer } from "./localize";
import { wizBuild, wizDefaults, type WizKind, type WizState } from "./rule-build";
import { ruleTokens, sentenceText } from "./rule-sentence";
import { shared, tokens } from "./styles";
import type { HomeAssistant, Rule } from "./types";

type Mode = "choose" | "wizard" | "template" | "import";

export class LaeutwerkNewRule extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @property({ attribute: false }) public localize!: Localizer;
  @state() private _mode: Mode = "choose";
  @state() private _step = 1;
  @state() private _w: WizState = wizDefaults(new Date().toISOString().slice(0, 10));
  @state() private _error?: string;
  @state() private _busy = false;

  private _emit(name: string, detail?: unknown): void {
    this.dispatchEvent(new CustomEvent(name, { detail }));
  }

  private _set<K extends keyof WizState>(key: K, value: WizState[K]): void {
    this._w = { ...this._w, [key]: value };
    this._error = undefined;
  }

  private _names = (id: string): string =>
    (this.hass?.states[id]?.attributes.friendly_name as string | undefined) ?? id;

  private _draft(): Rule {
    return wizBuild(this._w, this.localize);
  }

  private _missing(): string | undefined {
    const l = this.localize;
    const w = this._w;
    if (!w.name.trim()) return l.t("wiz_need_name");
    if ((w.kind === "cal" && !w.src) || (w.kind === "dev" && !w.dev)) return l.t("wiz_need_source");
    return undefined;
  }

  private async _finish(save: boolean): Promise<void> {
    const problem = this._missing();
    if (problem) {
      this._step = 1;
      this._error = problem;
      return;
    }
    const rule = this._draft();
    if (!save) return this._emit("pick", rule);
    if (!this.hass) return;
    this._busy = true;
    try {
      const saved = await this.hass.callWS<Rule>({ type: "laeutwerk/rules/create", rule });
      this._emit("created", saved);
    } catch (err) {
      this._error = String((err as { message?: string })?.message ?? err);
    } finally {
      this._busy = false;
    }
  }

  /** Target states offered for a device (HA's state picker knows the entity's options). */
  private _field(
    label: string,
    selector: Record<string, unknown>,
    value: unknown,
    set: (v: string) => void,
  ) {
    return html`<laeutwerk-field
      .hass=${this.hass}
      .localize=${this.localize}
      .label=${label}
      .selector=${selector}
      .value=${value}
      @value-changed=${(e: CustomEvent<{ value: unknown }>) => set(String(e.detail.value ?? ""))}
    ></laeutwerk-field>`;
  }

  private _input(
    label: string,
    type: string,
    value: string | number,
    set: (v: string) => void,
    width = "",
  ) {
    return html`<label class="fld"
      ><span class="hint">${label}</span
      ><input
        type=${type}
        style=${width}
        .value=${String(value)}
        @input=${(e: Event) => set((e.target as HTMLInputElement).value)}
    /></label>`;
  }

  private _tile(on: boolean, title: string, hint: string, click: () => void, icon = "") {
    return html`<button class="tile ${on ? "on" : ""}" @click=${click}>
      ${icon ? html`<ha-icon icon=${icon}></ha-icon>` : nothing}
      <span class="name">${title}</span><span class="sub">${hint}</span>
    </button>`;
  }

  private _renderChoose(): TemplateResult {
    const l = this.localize;
    return html`<div class="page">
      <div class="separator">${l.t("new_rule")}<span class="line"></span></div>
      <div class="tiles">
        ${this._tile(true, l.t("new_assistant"), l.t("new_assistant_hint"), () => (this._mode = "wizard"), "mdi:auto-fix")}
        ${this._tile(false, l.t("new_template"), l.t("new_template_hint"), () => (this._mode = "template"), "mdi:view-grid-outline")}
        ${this._tile(false, l.t("template_empty"), l.t("template_empty_hint"), () => this._emit("pick", emptyRule()), "mdi:plus")}
        ${this._tile(false, l.t("import_yaml"), l.t("new_import_hint"), () => (this._mode = "import"), "mdi:import")}
      </div>
      <div class="actions">
        <button class="pill outline" @click=${() => this._emit("cancel")}>${l.t("cancel")}</button>
      </div>
    </div>`;
  }

  private _renderQ1(): TemplateResult {
    const l = this.localize;
    const w = this._w;
    const kinds: [WizKind, string, string, string][] = [
      ["cal", "wiz_kind_cal", "wiz_kind_cal_hint", "mdi:calendar"],
      ["dev", "wiz_kind_dev", "wiz_kind_dev_hint", "mdi:flash-outline"],
      ["int", "wiz_kind_int", "wiz_kind_int_hint", "mdi:repeat"],
    ];
    return html`
      ${this._input(l.t("wiz_name"), "text", w.name, (v) => this._set("name", v))}
      <div class="hint">${l.t("wiz_kind")}</div>
      <div class="tiles">
        ${kinds.map(([k, t, h, icon]) =>
          this._tile(
            w.kind === k,
            l.t(t as "wiz_kind_cal"),
            l.t(h as "wiz_kind_cal_hint"),
            () => this._set("kind", k),
            icon,
          ),
        )}
      </div>
      ${
        w.kind === "cal"
          ? html`${this._field(l.t("wiz_calendar"), { entity: { domain: "calendar" } }, w.src, (v) => this._set("src", v))}
            ${this._input(l.t("wiz_keyword"), "text", w.kw, (v) => this._set("kw", v))}`
          : w.kind === "dev"
            ? html`${this._field(l.t("wiz_device"), { entity: {} }, w.dev, (v) => this._set("dev", v))}
                ${
                  w.dev
                    ? this._field(l.t("wiz_state"), { state: { entity_id: w.dev } }, w.devTo, (v) =>
                        this._set("devTo", v),
                      )
                    : nothing
                }
                <div class="hint">${l.t("wiz_dev_hint")}</div>`
            : html`<div class="row">
                ${this._input(l.t("wiz_every"), "number", w.ivN, (v) => this._set("ivN", Number(v)), "width:80px")}
                <label class="fld"
                  ><span class="hint">&nbsp;</span
                  ><select
                    @change=${(e: Event) => this._set("ivU", (e.target as HTMLSelectElement).value as "d" | "w")}
                  >
                    <option value="d" ?selected=${w.ivU === "d"}>${l.t("wiz_days")}</option>
                    <option value="w" ?selected=${w.ivU === "w"}>${l.t("wiz_weeks")}</option>
                  </select></label
                >
                ${this._input(l.t("wiz_first_due"), "date", w.ivStart, (v) => this._set("ivStart", v))}
              </div>`
      }
    `;
  }

  private _renderQ2(): TemplateResult {
    const l = this.localize;
    const w = this._w;
    if (w.kind === "cal") {
      const opts: [WizState["when"], "wiz_dm1" | "wiz_d0" | "wiz_rb"][] = [
        ["dm1", "wiz_dm1"],
        ["d0", "wiz_d0"],
        ["rb", "wiz_rb"],
      ];
      return html`<div class="hint">${l.t("wiz_when_q")}</div>
        <div class="tiles">
          ${opts.map(([k, t]) =>
            this._tile(w.when === k, l.t(t), l.t(`${t}_hint` as "wiz_dm1_hint"), () =>
              this._set("when", k),
            ),
          )}
        </div>
        ${
          w.when === "rb"
            ? this._input(
                l.t("wiz_hours"),
                "number",
                w.hrs,
                (v) => this._set("hrs", Number(v)),
                "width:100px",
              )
            : this._input(
                l.t("wiz_clock"),
                "time",
                w.time,
                (v) => this._set("time", v),
                "width:140px",
              )
        }`;
    }
    const check = (text: string) =>
      html`<label class="check"
        ><input
          type="checkbox"
          .checked=${w.rep}
          @change=${(e: Event) => this._set("rep", (e.target as HTMLInputElement).checked)}
        />${text}</label
      >`;
    return w.kind === "dev"
      ? html`${check(l.t("wiz_follow_dev"))}
        ${w.rep ? this._input(l.t("wiz_follow_min"), "number", w.repMin, (v) => this._set("repMin", Number(v)), "width:100px") : nothing}`
      : html`${this._input(l.t("wiz_clock"), "time", w.time, (v) => this._set("time", v), "width:140px")}
        ${check(l.t("wiz_follow_iv"))}`;
  }

  private _renderWizard(): TemplateResult {
    const l = this.localize;
    const sentence = sentenceText(ruleTokens(this._draft(), l, this._names));
    return html`<div class="page">
      <div class="separator">${l.t("wiz_title")}<span class="line"></span></div>
      <div class="steps">
        ${([1, 2] as const).map(
          (n) =>
            html`<button
              class="chip ${this._step === n ? "on" : ""}"
              @click=${() => (this._step = n)}
            >
              ${n}. ${l.t(n === 1 ? "wiz_q1" : "wiz_q2")}
            </button>`,
        )}
      </div>
      ${this._step === 1 ? this._renderQ1() : this._renderQ2()}
      <div class="sum">
        <div class="hint">${l.t("wiz_sound")}</div>
        <div>${sentence}</div>
      </div>
      ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
      <div class="actions">
        <button class="pill outline" @click=${() => (this._mode = "choose")}>${l.t("back")}</button>
        <button class="pill outline" @click=${() => void this._finish(false)}>
          ${l.t("wiz_details")}
        </button>
        ${
          this._step === 1
            ? html`<button class="pill primary" @click=${() => (this._step = 2)}>
                ${l.t("wiz_next")}
              </button>`
            : html`<button
                class="pill primary"
                ?disabled=${this._busy}
                @click=${() => void this._finish(true)}
              >
                ${l.t("wiz_create")}
              </button>`
        }
      </div>
    </div>`;
  }

  protected render(): TemplateResult {
    if (this._mode === "wizard") return this._renderWizard();
    if (this._mode === "template" || this._mode === "import") {
      return html`<laeutwerk-template-picker
        .hass=${this.hass}
        .localize=${this.localize}
        .mode=${this._mode === "import" ? "import" : "templates"}
        @pick=${(e: CustomEvent<{ rule: Rule }>) => this._emit("pick", e.detail.rule)}
        @imported=${() => this._emit("imported")}
        @cancel=${() => (this._mode = "choose")}
      ></laeutwerk-template-picker>`;
    }
    return this._renderChoose();
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
      .tiles {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 10px;
      }
      .tile {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        gap: 4px;
        min-height: 88px;
        padding: 12px;
        border-radius: 18px;
        background: var(--lw-surface);
        text-align: left;
      }
      .tile.on {
        box-shadow: inset 0 0 0 1.5px var(--lw-accent);
      }
      .tile .sub {
        white-space: normal;
      }
      .steps,
      .row {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: flex-end;
      }
      .fld {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
      .check {
        display: flex;
        gap: 8px;
        align-items: center;
        min-height: 44px;
      }
      .sum {
        padding: 12px;
        border-radius: 18px;
        background: var(--lw-surface-2);
      }
    `,
  ];
}
