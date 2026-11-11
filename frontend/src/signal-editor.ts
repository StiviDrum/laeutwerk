/**
 * "Signal bearbeiten" (DESIGN C1.3): type tiles, when (now / opportunity with
 * HA's trigger editor), only if (all / any + HA's condition editor), the
 * fields of the type, limits, test and "as YAML".
 */
import { LitElement, css, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import { SIGNAL_ICONS, availableVariables, defaultSignal, renderTemplate } from "./format";
import type { Localizer, StringKey } from "./localize";
import { shared, tokens } from "./styles";
import type { HaConfig, HomeAssistant, PushButton, QuietTime, Rule, Signal } from "./types";

const TYPES: Signal["type"][] = ["notify", "light_signal", "announce", "action"];
/** Shared empty list: a new [] on every render would look like a new value. */
const EMPTY: never[] = [];

function list(value: unknown): HaConfig[] {
  if (Array.isArray(value)) return value as HaConfig[];
  return value && typeof value === "object" ? [value as HaConfig] : [];
}

export class LaeutwerkSignalEditor extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @property({ attribute: false }) public localize!: Localizer;
  @property({ attribute: false }) public rule!: Rule;
  /**
   * Signal to edit. Never written by this element: Lit re-sets object
   * properties on every parent render, so edits live in the copy `_sig`
   * (changing this property would reset the editor on each HA update).
   */
  @property({ attribute: false }) public signal!: Signal;
  @state() private _sig!: Signal;
  /** Variables of the next real event (preview of the texts). */
  @property({ attribute: false }) public sample: Record<string, string> = {};
  /** Saved rule id: testing needs a saved rule. */
  @property({ attribute: false }) public ruleId?: string;
  @state() private _yaml = false;
  @state() private _yamlError?: string;
  @state() private _testState?: string;
  @state() private _focus = "message";

  protected willUpdate(changed: PropertyValues): void {
    if (changed.has("signal") && this.signal) {
      this._sig = JSON.parse(JSON.stringify(this.signal)) as Signal;
    }
  }

  private get _l(): Localizer {
    return this.localize;
  }

  private _set(changes: Partial<Signal>): void {
    const next = { ...this._sig, ...changes } as Signal & Record<string, unknown>;
    for (const [key, value] of Object.entries(changes)) {
      if (value === undefined || value === "") delete next[key];
    }
    this._sig = next;
  }

  private _emit(name: "apply" | "cancel" | "delete"): void {
    this.dispatchEvent(new CustomEvent(name, { detail: { signal: this._sig } }));
  }

  private _setType(type: Signal["type"]): void {
    if (type === this._sig.type) return;
    const fresh = defaultSignal(type, this.rule);
    this._sig = {
      ...fresh,
      id: this._sig.id,
      when: this._sig.when,
      conditions: this._sig.conditions,
      conditions_match: this._sig.conditions_match,
      quiet: this._sig.quiet,
    };
  }

  private _insertVariable(name: string): void {
    const key = this._focus as keyof Signal;
    const current = String(this._sig[key] ?? "");
    this._set({ [key]: `${current}${current && !current.endsWith(" ") ? " " : ""}{${name}}` });
  }

  private async _test(): Promise<void> {
    if (!this.hass || !this.ruleId) return;
    this._testState = "…";
    try {
      const config = { ...this._sig };
      delete config.id;
      await this.hass.callService("laeutwerk", "test_signal", { rule: this.ruleId, config });
      this._testState = this._l.t("test_sent");
    } catch (err) {
      this._testState = this._l.t("failed", {
        error:
          err && typeof err === "object" && "message" in err ? String(err.message) : String(err),
      });
    }
  }

  private _toggleYaml(): void {
    if (this._yaml) {
      if (this._yamlError) return;
      this._yaml = false;
      return;
    }
    this._yamlError = undefined;
    this._yaml = true;
  }

  private _onYaml(ev: CustomEvent<{ value: unknown }>): void {
    const value = ev.detail.value;
    if (value && typeof value === "object" && !Array.isArray(value) && "type" in value) {
      this._sig = value as Signal;
      this._yamlError = undefined;
    } else {
      this._yamlError = "type";
    }
  }

  // --- render ---------------------------------------------------------------

  protected render() {
    const l = this._l;
    const s = this._sig;
    if (this._yaml) {
      return html`<div class="page">
        <div class="separator">${l.t("edit_signal")}<span class="line"></span></div>
        <laeutwerk-field
          .hass=${this.hass}
          .localize=${l}
          .selector=${{ object: {} }}
          .value=${s}
          label="YAML"
          @value-changed=${this._onYaml}
        ></laeutwerk-field>
        ${this._footer()}
      </div>`;
    }
    const opportunity = s.when !== "now";
    return html`<div class="page">
      <div class="separator">${l.t("edit_signal")}<span class="line"></span></div>

      <div class="panel">
        <div class="step">${l.t("sig_type")}</div>
        <div class="tiles">
          ${TYPES.map(
            (type) =>
              html`<button
                class="tile"
                aria-pressed=${type === s.type}
                @click=${() => this._setType(type)}
              >
                <ha-icon .icon=${SIGNAL_ICONS[type]}></ha-icon>
                <span>${l.t(`type_${type}` as StringKey)}</span>
              </button>`,
          )}
        </div>
      </div>

      <div class="panel">
        <div class="step">${l.t("sig_when")}</div>
        <div class="segmented">
          <button aria-pressed=${!opportunity} @click=${() => this._set({ when: "now" })}>
            ${l.t("when_now")}
          </button>
          <button
            aria-pressed=${opportunity}
            @click=${() =>
              !opportunity && this._set({ when: { opportunity: [], manual_only: false } })}
          >
            ${l.t("when_opportunity")}
          </button>
        </div>
        ${opportunity ? this._opportunity() : nothing}
      </div>

      <div class="panel">
        <div class="row">
          <div class="step grow">${l.t("sig_only_if")}</div>
          <div class="segmented small">
            ${(["all", "any"] as const).map(
              (m) =>
                html`<button
                  aria-pressed=${(s.conditions_match ?? "all") === m}
                  @click=${() => this._set({ conditions_match: m })}
                >
                  ${l.t(m === "all" ? "match_all" : "match_any")}
                </button>`,
            )}
          </div>
        </div>
        <laeutwerk-field
          .hass=${this.hass}
          .localize=${l}
          .selector=${{ condition: {} }}
          .value=${s.conditions ?? EMPTY}
          @value-changed=${(e: CustomEvent<{ value: unknown }>) => {
            const value = list(e.detail.value);
            this._set({ conditions: value.length ? value : undefined });
          }}
        ></laeutwerk-field>
      </div>

      <div class="panel">
        <div class="step">${l.t("sig_what")}</div>
        ${this._fields()}
      </div>

      <div class="panel">
        <div class="step">${l.t("sig_limits")}</div>
        ${this._stage()} ${this._limits()}
      </div>

      ${this._footer()}
    </div>`;
  }

  private _opportunity(): TemplateResult {
    const l = this._l;
    const when = this._sig.when as { opportunity: HaConfig | HaConfig[]; manual_only?: boolean };
    return html`
      <div class="hint">${l.t("when_opportunity_hint")}</div>
      <laeutwerk-field
        .hass=${this.hass}
        .localize=${l}
        .selector=${{ trigger: {} }}
        .value=${list(when.opportunity)}
        @value-changed=${(e: CustomEvent<{ value: unknown }>) =>
          this._set({ when: { ...when, opportunity: list(e.detail.value) } })}
      ></laeutwerk-field>
      ${this._toggle(l.t("manual_only"), !!when.manual_only, (v) =>
        this._set({ when: { ...when, manual_only: v } }),
      )}
    `;
  }

  private _fields(): TemplateResult {
    const s = this._sig;
    if (s.type === "notify") return this._notifyFields();
    if (s.type === "light_signal") return this._lightFields();
    if (s.type === "announce") return this._announceFields();
    return html`<laeutwerk-field
        .hass=${this.hass}
        .localize=${this._l}
        .selector=${{ action: {} }}
        .value=${list(s.actions)}
        @value-changed=${(e: CustomEvent<{ value: unknown }>) =>
          this._set({ actions: list(e.detail.value) })}
      ></laeutwerk-field>
      ${this._variables(false)}`;
  }

  private _notifyFields(): TemplateResult {
    const l = this._l;
    const s = this._sig;
    const buttons = (s.actions ?? []) as PushButton[];
    const ack = buttons.find((b) => b.ack);
    const snooze = buttons.find((b) => b.snooze !== undefined);
    const setButtons = (nextAck?: PushButton, nextSnooze?: PushButton) =>
      this._set({ actions: [nextAck, nextSnooze].filter((b): b is PushButton => !!b) });
    return html`
      <label class="field"
        >${l.t("audience")}
        <select
          .value=${s.audience ?? ""}
          @change=${(e: Event) =>
            this._set({
              audience: ((e.target as HTMLSelectElement).value || undefined) as Signal["audience"],
            })}
        >
          ${(
            ["", "all", "present", "persons", ...(this.rule.assignee ? ["assignee"] : [])] as const
          ).map(
            (a) =>
              html`<option value=${a} ?selected=${(s.audience ?? "") === a}>
                ${l.t(a ? (`audience_${a}` as StringKey) : "audience_none")}
              </option>`,
          )}
        </select>
      </label>
      ${
        s.audience === "persons"
          ? html`<laeutwerk-field
              .hass=${this.hass}
              .localize=${l}
              .label=${l.t("persons")}
              .selector=${{ entity: { domain: "person", multiple: true } }}
              .value=${s.persons ?? EMPTY}
              @value-changed=${(e: CustomEvent<{ value: string[] }>) =>
                this._set({ persons: e.detail.value })}
            ></laeutwerk-field>`
          : nothing
      }
      <label class="field"
        >${l.t("targets")}
        <input
          .value=${(s.targets ?? []).join(", ")}
          placeholder="notify.mobile_app_…"
          @change=${(e: Event) => {
            const targets = (e.target as HTMLInputElement).value
              .split(",")
              .map((t) => t.trim())
              .filter(Boolean);
            this._set({ targets: targets.length ? targets : undefined });
          }}
        />
        <span class="hint">${l.t("targets_hint")}</span>
      </label>
      ${this._text("title", l.t("push_title"))} ${this._text("message", l.t("push_message"), true)}
      ${this._variables(false)}
      <div class="sublabel">${l.t("push_buttons")}</div>
      ${this._toggle(l.t("btn_done"), !!ack, (v) =>
        setButtons(
          v ? { ack: true, label: this.rule.ack_label || l.t("done") } : undefined,
          snooze,
        ),
      )}
      ${
        ack
          ? html`<input
              .value=${ack.label}
              @input=${(e: Event) =>
                setButtons({ ...ack, label: (e.target as HTMLInputElement).value }, snooze)}
            />`
          : nothing
      }
      ${this._toggle(l.t("btn_snooze"), !!snooze, (v) =>
        setButtons(ack, v ? { snooze: "3h", label: l.t("later") } : undefined),
      )}
      ${
        snooze
          ? html`<div class="row">
              <input
                class="grow"
                .value=${snooze.label}
                @input=${(e: Event) =>
                  setButtons(ack, { ...snooze, label: (e.target as HTMLInputElement).value })}
              />
              <input
                style="width:84px"
                aria-label=${l.t("btn_snooze_duration")}
                .value=${String(snooze.snooze)}
                @input=${(e: Event) =>
                  setButtons(ack, { ...snooze, snooze: (e.target as HTMLInputElement).value })}
              />
            </div>`
          : nothing
      }
    `;
  }

  private _lightFields(): TemplateResult {
    const l = this._l;
    const s = this._sig;
    const columns = this.rule.filter.keywords.columns;
    const fromColumn = s.color_from !== undefined;
    return html`
      <laeutwerk-field
        .hass=${this.hass}
        .localize=${l}
        .label=${l.t("lights")}
        .selector=${{ entity: { domain: "light", multiple: true } }}
        .value=${s.entities ?? EMPTY}
        @value-changed=${(e: CustomEvent<{ value: string[] }>) => this._set({ entities: e.detail.value })}
      ></laeutwerk-field>
      <div class="row">
        <div class="segmented grow">
          ${(["blink", "pulse"] as const).map(
            (effect) =>
              html`<button
                aria-pressed=${(s.pattern?.effect ?? "blink") === effect}
                @click=${() => this._set({ pattern: { ...s.pattern, effect } })}
              >
                ${l.t(effect === "blink" ? "effect_blink" : "effect_pulse")}
              </button>`,
          )}
        </div>
        <label class="field"
          >${l.t("count")}
          <input
            type="number"
            min="1"
            max="20"
            .value=${String(s.pattern?.count ?? 3)}
            @change=${(e: Event) =>
              this._set({
                pattern: { ...s.pattern, count: Number((e.target as HTMLInputElement).value) },
              })}
          />
        </label>
      </div>
      <div class="sublabel">${l.t("light_color")}</div>
      <div class="segmented">
        <button aria-pressed=${!fromColumn} @click=${() => this._set({ color_from: undefined })}>
          ${l.t("color_fixed")}
        </button>
        <button
          aria-pressed=${fromColumn}
          ?disabled=${!columns.length}
          @click=${() => this._set({ color_from: columns[0], color: undefined })}
        >
          ${l.t("color_from")}
        </button>
      </div>
      ${
        fromColumn
          ? html`<select
              .value=${s.color_from ?? ""}
              @change=${(e: Event) => this._set({ color_from: (e.target as HTMLSelectElement).value })}
            >
              ${columns.map((c) => html`<option value=${c} ?selected=${c === s.color_from}>{${c}}</option>`)}
            </select>`
          : html`<input
              .value=${s.color ?? ""}
              placeholder=${l.t("color_placeholder")}
              @input=${(e: Event) => this._set({ color: (e.target as HTMLInputElement).value })}
            />`
      }
      <label class="field"
        >${l.t("brightness")}
        <input
          type="number"
          min="1"
          max="100"
          .value=${String(s.brightness ?? 100)}
          @change=${(e: Event) => this._set({ brightness: Number((e.target as HTMLInputElement).value) })}
        />
      </label>
      ${this._toggle(l.t("restore"), s.restore !== false, (v) => this._set({ restore: v }))}
    `;
  }

  private _announceFields(): TemplateResult {
    const l = this._l;
    const s = this._sig;
    return html`
      <laeutwerk-field
        .hass=${this.hass}
        .localize=${l}
        .label=${l.t("players")}
        .selector=${{ entity: { domain: "media_player", multiple: true } }}
        .value=${s.players ?? EMPTY}
        @value-changed=${(e: CustomEvent<{ value: string[] }>) => this._set({ players: e.detail.value })}
      ></laeutwerk-field>
      <div class="row">
        <label class="field"
          >${l.t("volume")}
          <input
            type="number"
            min="0"
            max="100"
            .value=${s.volume === undefined ? "" : String(s.volume)}
            @change=${(e: Event) => {
              const raw = (e.target as HTMLInputElement).value;
              this._set({ volume: raw === "" ? undefined : Number(raw) });
            }}
          />
        </label>
        <laeutwerk-field
          class="grow"
          .hass=${this.hass}
          .localize=${l}
          .label=${l.t("tts_engine")}
          .selector=${{ entity: { domain: "tts" } }}
          .value=${s.tts ?? ""}
          @value-changed=${(e: CustomEvent<{ value: string }>) =>
            this._set({ tts: e.detail.value || undefined })}
        ></laeutwerk-field>
      </div>
      ${this._text("text", l.t("spoken_text"), true)} ${this._variables(false)}
    `;
  }

  /** Text field with its plural variant and a live preview. */
  private _text(
    key: "title" | "message" | "text",
    label: string,
    multiline = false,
  ): TemplateResult {
    const l = this._l;
    const s = this._sig;
    const pluralKey = `${key}_plural` as "title_plural" | "message_plural" | "text_plural";
    const input = (k: typeof key | typeof pluralKey) => {
      const value = String(s[k] ?? "");
      const onInput = (e: Event) =>
        this._set({ [k]: (e.target as HTMLInputElement | HTMLTextAreaElement).value });
      return multiline
        ? html`<textarea
            .value=${value}
            @focus=${() => (this._focus = k)}
            @input=${onInput}
          ></textarea>`
        : html`<input .value=${value} @focus=${() => (this._focus = k)} @input=${onInput} />`;
    };
    const preview = renderTemplate(s[key], this.sample);
    return html`
      <label class="field">${label} ${input(key)}</label>
      <label class="field">${l.t("plural_variant")} ${input(pluralKey)}</label>
      ${
        preview && Object.keys(this.sample).length
          ? html`<div class="preview">
              <ha-icon icon="mdi:eye-outline"></ha-icon><span>${preview}</span>
            </div>`
          : nothing
      }
    `;
  }

  private _variables(opportunityOnly: boolean): TemplateResult {
    const names = availableVariables(this.rule, this._sig.when !== "now" || opportunityOnly);
    return html`<div class="wrap vars" aria-label=${this._l.t("variables")}>
      ${names.map(
        (name) =>
          html`<button class="chip" @click=${() => this._insertVariable(name)}>{${name}}</button>`,
      )}
    </div>`;
  }

  private _stage(): TemplateResult | typeof nothing {
    const stages = this.rule.escalation?.length ?? 0;
    if (!stages) return nothing;
    const l = this._l;
    return html`<label class="field"
      >${l.t("stage")}
      <select
        @change=${(e: Event) => {
          const stage = Number((e.target as HTMLSelectElement).value);
          this._set({ stage: stage || undefined });
        }}
      >
        ${Array.from({ length: stages + 1 }, (_, n) => n).map(
          (n) =>
            html`<option value=${n} ?selected=${(this._sig.stage ?? 0) === n}>
              ${n ? `${l.t("stage_n", { n })} · ${this.rule.escalation![n - 1].after}` : l.t("stage_0")}
            </option>`,
        )}
      </select>
    </label>`;
  }

  private _limits(): TemplateResult {
    const l = this._l;
    const s = this._sig;
    const limit = s.limit ?? {};
    const setLimit = (key: "per_reminder" | "min_interval", raw: string) => {
      const next = { ...limit, [key]: raw === "" ? undefined : Number(raw) };
      if (next[key] === undefined) delete next[key];
      this._set({ limit: Object.keys(next).length ? next : undefined });
    };
    const quiet = s.quiet ?? [];
    const setQuiet = (index: number, changes: Partial<QuietTime> | null) => {
      const next = quiet
        .map((q, i) => (i === index ? (changes ? { ...q, ...changes } : null) : q))
        .filter((q): q is QuietTime => !!q);
      this._set({ quiet: next.length ? next : undefined });
    };
    return html`
      <div class="row bottom">
        <label class="field grow"
          >${l.t("per_reminder")}
          <input
            type="number"
            min="1"
            .value=${limit.per_reminder === undefined ? "" : String(limit.per_reminder)}
            @change=${(e: Event) => setLimit("per_reminder", (e.target as HTMLInputElement).value)}
          />
        </label>
        <label class="field grow"
          >${l.t("min_interval")}
          <input
            type="number"
            min="1"
            .value=${limit.min_interval === undefined ? "" : String(limit.min_interval)}
            @change=${(e: Event) => setLimit("min_interval", (e.target as HTMLInputElement).value)}
          />
        </label>
      </div>
      <div class="sublabel">${l.t("quiet_times")}</div>
      ${quiet.map(
        (q, i) =>
          html`<div class="row quiet">
            <input
              type="time"
              .value=${q.from}
              @change=${(e: Event) => setQuiet(i, { from: (e.target as HTMLInputElement).value })}
            />
            <span>–</span>
            <input
              type="time"
              .value=${q.to}
              @change=${(e: Event) => setQuiet(i, { to: (e.target as HTMLInputElement).value })}
            />
            <select
              class="grow"
              @change=${(e: Event) =>
                setQuiet(i, { mode: (e.target as HTMLSelectElement).value as QuietTime["mode"] })}
            >
              <option value="skip" ?selected=${q.mode !== "defer"}>${l.t("quiet_skip")}</option>
              <option value="defer" ?selected=${q.mode === "defer"}>${l.t("quiet_defer")}</option>
            </select>
            <button class="mini" aria-label=${l.t("remove")} @click=${() => setQuiet(i, null)}>
              <ha-icon icon="mdi:close"></ha-icon>
            </button>
          </div>`,
      )}
      <div class="wrap">
        <button
          class="chip dashed"
          @click=${() => this._set({ quiet: [...quiet, { from: "22:00", to: "08:00", mode: "skip" }] })}
        >
          <ha-icon icon="mdi:plus"></ha-icon>${l.t("add_quiet")}
        </button>
      </div>
    `;
  }

  private _toggle(label: string, value: boolean, onChange: (v: boolean) => void): TemplateResult {
    return html`<div class="toggle">
      <span>${label}</span>
      <button
        class="switch"
        role="switch"
        aria-checked=${value}
        aria-label=${label}
        @click=${() => onChange(!value)}
      >
        <span></span>
      </button>
    </div>`;
  }

  private _footer(): TemplateResult {
    const l = this._l;
    return html`
      <div class="row">
        <button class="chip" ?disabled=${!this.ruleId} @click=${this._test}>
          <ha-icon icon="mdi:play-outline"></ha-icon>${l.t("test")}
        </button>
        <span class="hint grow"
          >${this.ruleId ? (this._testState ?? "") : l.t("test_needs_save")}</span
        >
        <button class="chip" @click=${this._toggleYaml}>
          <ha-icon icon="mdi:code-braces"></ha-icon>${this._yaml ? l.t("as_form") : l.t("as_yaml")}
        </button>
      </div>
      <button class="pill danger wide" @click=${() => this._emit("delete")}>
        ${l.t("delete")}
      </button>
      <div class="actions">
        <button class="pill outline" @click=${() => this._emit("cancel")}>${l.t("cancel")}</button>
        <button
          class="pill primary"
          ?disabled=${!!this._yamlError}
          @click=${() => this._emit("apply")}
        >
          ${l.t("apply")}
        </button>
      </div>
    `;
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
        grid-template-columns: repeat(4, 1fr);
        gap: 8px;
      }
      .tile {
        min-height: 64px;
        border-radius: 16px;
        background: var(--lw-surface);
        border: 2px solid transparent;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 4px;
        font-size: 12px;
        font-weight: 600;
      }
      .tile[aria-pressed="true"] {
        border-color: var(--lw-accent);
      }
      .segmented.small button {
        min-height: 32px;
        padding: 0 12px;
      }
      .sublabel {
        font-size: 12px;
        font-weight: 600;
        color: var(--lw-text-2);
        margin-top: 4px;
      }
      .vars .chip {
        min-height: 32px;
        font-family: ui-monospace, monospace;
      }
      .preview {
        display: flex;
        gap: 8px;
        align-items: flex-start;
        font-size: 13px;
        padding: 10px 12px;
        border-radius: 12px;
        background: var(--lw-surface-2);
      }
      .preview ha-icon {
        --mdc-icon-size: 16px;
        color: var(--lw-text-2);
      }
      .quiet {
        flex-wrap: wrap;
      }
      .quiet select {
        flex: 1 1 140px;
      }
      .row.bottom {
        align-items: flex-end;
      }
    `,
  ];
}
