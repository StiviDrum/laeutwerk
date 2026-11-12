/**
 * "Signal bearbeiten" (DESIGN C1.3): type tiles, when (now / opportunity with
 * HA's trigger editor), only if (all / any + HA's condition editor), the
 * fields of the type, limits, test and "as YAML".
 */
import { LitElement, css, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import {
  SIGNAL_ICONS,
  availableVariables,
  colorNameToHex,
  columnNames,
  defaultSignal,
  mapTargetsToPersons,
  renderTemplate,
} from "./format";
import type { Localizer, StringKey } from "./localize";
import { helpTip } from "./help-tip";
import { shared, tokens } from "./styles";
import type {
  HaConfig,
  HomeAssistant,
  PersonInfo,
  PushButton,
  QuietTime,
  Rule,
  Signal,
} from "./types";

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
  /** Colours of the next matches (#rrggbb) – shown for "colour from column". */
  @property({ attribute: false }) public swatches: string[] = [];
  @state() private _yaml = false;
  @state() private _yamlError?: string;
  @state() private _testState?: string;
  /** Persons with their phones (laeutwerk/persons), loaded once. */
  @state() private _persons?: PersonInfo[];
  /** Household quiet time (laeutwerk/settings), loaded once. */
  @state() private _householdQuiet: QuietTime[] | null = null;
  /** Open sections (collapsible like the steps of the rule editor). */
  @state() private _openSec = new Set<string>(["what", "texts"]);

  public connectedCallback(): void {
    super.connectedCallback();
    if (this._persons === undefined && this.hass) {
      this.hass
        .callWS<{ persons: PersonInfo[] }>({ type: "laeutwerk/persons" })
        .then((res) => (this._persons = res.persons))
        .catch(() => (this._persons = []));
    }
    if (this.hass) {
      this.hass
        .callWS<{ quiet: QuietTime[] | null }>({ type: "laeutwerk/settings" })
        .then((res) => (this._householdQuiet = res.quiet?.length ? res.quiet : null))
        .catch(() => undefined);
    }
  }

  protected willUpdate(changed: PropertyValues): void {
    if (changed.has("signal") && this.signal) {
      this._sig = JSON.parse(JSON.stringify(this.signal)) as Signal;
      this._openSec = new Set(["what", "texts"]);
    }
    if ((changed.has("signal") || changed.has("_persons")) && this._sig && this._persons) {
      const mapped = mapTargetsToPersons(this._sig, this._persons);
      if (mapped !== this._sig) this._sig = mapped;
    }
  }

  private _toggleSec(key: string): void {
    const next = new Set(this._openSec);
    if (!next.delete(key)) next.add(key);
    this._openSec = next;
  }

  /** A collapsible section: title, a short summary when closed, the body when open. */
  private _section(
    key: string,
    title: string,
    summary: string,
    body: () => TemplateResult,
    sub = false,
  ): TemplateResult {
    const open = this._openSec.has(key);
    return html`<section class=${sub ? "subsec" : "panel"} data-sec=${key}>
      <button
        class="head ${sub ? "small" : "step"}"
        aria-expanded=${open}
        @click=${() => this._toggleSec(key)}
      >
        <span class="grow text">
          <span>${title}</span>
          ${open || !summary ? nothing : html`<span class="summary">${summary}</span>`}
        </span>
        <ha-icon .icon=${open ? "mdi:chevron-up" : "mdi:chevron-down"}></ha-icon>
      </button>
      ${open ? html`<div class="body">${body()}</div>` : nothing}
    </section>`;
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
    const fresh = defaultSignal(type, this.rule, this._l.t("done"));
    this._sig = {
      ...fresh,
      id: this._sig.id,
      when: this._sig.when,
      conditions: this._sig.conditions,
      conditions_match: this._sig.conditions_match,
      quiet: this._sig.quiet,
    };
  }

  private async _test(): Promise<void> {
    if (!this.hass) return;
    this._testState = "…";
    try {
      const signal = { ...this._sig };
      delete signal.id;
      // The rule as it is in the editor – saved or not.
      const rule = { ...this.rule, signals: [] };
      await this.hass.callWS({ type: "laeutwerk/test_signal", rule, signal });
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
    const conditions = s.conditions?.length ?? 0;
    return html`<div class="page">
      <div class="separator">${l.t("edit_signal")}<span class="line"></span></div>

      ${this._section("type", l.t("sig_type"), l.t(`type_${s.type}` as StringKey), () => this._typeBody())}
      ${this._section(
        "when",
        l.t("sig_when"),
        opportunity ? l.t("when_opportunity") : l.t("when_now"),
        () => this._whenBody(),
      )}
      ${this._section(
        "only_if",
        l.t("sig_only_if"),
        conditions ? l.t("sum_conditions", { n: conditions }) : l.t("sum_no_conditions"),
        () => this._onlyIfBody(),
      )}
      ${this._section("what", l.t("sig_what"), this._whatSummary(), () => this._fields())}
      ${this._section(
        "limits",
        l.t("sig_limits"),
        this._limitsSummary(),
        () => html`${this._stage()} ${this._limits()}`,
      )}
      ${this._footer()}
    </div>`;
  }

  private _typeBody(): TemplateResult {
    const l = this._l;
    const s = this._sig;
    return html`<div class="tiles">
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
    </div>`;
  }

  private _whenBody(): TemplateResult {
    const l = this._l;
    const opportunity = this._sig.when !== "now";
    return html`<div class="row">
        <div class="segmented grow">
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
        ${helpTip(l, "help_when")}
      </div>
      ${opportunity ? this._opportunity() : nothing}`;
  }

  private _onlyIfBody(): TemplateResult {
    const l = this._l;
    const s = this._sig;
    return html`<div class="row">
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
        ${helpTip(l, "help_only_if")}
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
      ></laeutwerk-field>`;
  }

  /** Short summary of "what happens" for the closed section. */
  private _whatSummary(): string {
    const s = this._sig;
    const names = (ids: string[] | undefined) =>
      (ids ?? [])
        .map((id) => (this.hass?.states[id]?.attributes.friendly_name as string | undefined) ?? id)
        .join(", ");
    if (s.type === "notify")
      return [this._recipientsSummary(), s.title].filter(Boolean).join(" · ");
    if (s.type === "light_signal") return names(s.entities);
    if (s.type === "announce") return names(s.players);
    const count = list(s.actions).length;
    return count ? this._l.t("sum_actions", { n: count }) : "";
  }

  private _limitsSummary(): string {
    const l = this._l;
    const s = this._sig;
    const bits: string[] = [];
    if (s.stage) bits.push(l.t("stage_n", { n: s.stage }));
    if (s.limit?.per_reminder) bits.push(l.t("s_max", { n: s.limit.per_reminder }));
    if (s.quiet?.length) bits.push(`${l.t("quiet_times")}: ${s.quiet.length}`);
    return bits.join(" · ");
  }

  private _recipientsSummary(): string {
    const l = this._l;
    const s = this._sig;
    if (s.audience === "assignee") return l.t("push_to_assignee");
    const persons = this._persons ?? [];
    const ids =
      s.audience === "all" || s.audience === "present"
        ? persons.map((p) => p.entity_id)
        : (s.persons ?? []);
    const named = ids.map((id) => persons.find((p) => p.entity_id === id)?.name ?? id);
    const text = named.join(", ");
    return s.audience === "present" || s.only_present ? `${text} (${l.t("only_present")})` : text;
  }

  private _opportunity(): TemplateResult {
    const l = this._l;
    const when = this._sig.when as { opportunity: HaConfig | HaConfig[]; manual_only?: boolean };
    return html`
      <laeutwerk-field
        .hass=${this.hass}
        .localize=${l}
        .selector=${{ trigger: {} }}
        .value=${list(when.opportunity)}
        @value-changed=${(e: CustomEvent<{ value: unknown }>) =>
          this._set({ when: { ...when, opportunity: list(e.detail.value) } })}
      ></laeutwerk-field>
      ${this._toggle(
        l.t("manual_only"),
        !!when.manual_only,
        (v) => this._set({ when: { ...when, manual_only: v } }),
        "help_manual_only",
      )}
    `;
  }

  private _fields(): TemplateResult {
    const s = this._sig;
    const l = this._l;
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
      <div class="sublabel tiprow">
        ${l.t("variables")}${html`<laeutwerk-help-tip
          .text=${l.t("help_action_vars", {
            list: this._variableNames()
              .map((n) => `{${n}}`)
              .join(" "),
          })}
          .label=${l.t("help")}
        ></laeutwerk-help-tip>`}
      </div>`;
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
      ${this._section(
        "recipients",
        l.t("sec_recipients"),
        this._recipientsSummary(),
        () => this._recipients(),
        true,
      )}
      ${this._section(
        "texts",
        l.t("sec_texts"),
        renderTemplate(s.title, this.sample) || s.title || "",
        () =>
          html`${this._text("title", l.t("push_title"))}
          ${this._text("message", l.t("push_message"), true)}`,
        true,
      )}
      ${this._section(
        "buttons",
        l.t("sec_buttons"),
        buttons.map((b) => b.label).join(" · "),
        () => this._buttons(ack, snooze, setButtons),
        true,
      )}
    `;
  }

  private _buttons(
    ack: PushButton | undefined,
    snooze: PushButton | undefined,
    setButtons: (nextAck?: PushButton, nextSnooze?: PushButton) => void,
  ): TemplateResult {
    const l = this._l;
    return html`
      ${this._toggle(l.t("btn_done"), !!ack, (v) =>
        setButtons(v ? { ack: true, label: l.t("done") } : undefined, snooze),
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

  /** Push recipients: tick persons (their phones), optionally only who is home. */
  private _recipients(): TemplateResult {
    const l = this._l;
    const s = this._sig;
    const persons = this._persons ?? [];
    const all = persons.map((p) => p.entity_id);
    const toAssignee = s.audience === "assignee";
    const ticked =
      s.audience === "all" || s.audience === "present"
        ? all
        : s.audience === "persons"
          ? (s.persons ?? [])
          : [];
    const onlyPresent = s.audience === "present" || !!s.only_present;
    const setPersons = (next: string[], present: boolean) =>
      this._set(
        next.length
          ? { audience: "persons", persons: next, only_present: present || undefined }
          : { audience: undefined, persons: undefined, only_present: undefined },
      );
    return html`
      ${
        this.rule.assignee
          ? this._toggle(l.t("push_to_assignee"), toAssignee, (v) =>
              v
                ? this._set({ audience: "assignee", persons: undefined, only_present: undefined })
                : setPersons(all, onlyPresent),
            )
          : nothing
      }
      ${
        toAssignee
          ? nothing
          : html`
              ${
                this._persons === undefined
                  ? html`<div class="hint">${l.t("loading")}</div>`
                  : persons.length
                    ? html`<div class="persons divided">
                        ${persons.map((p) => {
                          const on = ticked.includes(p.entity_id);
                          return html`<button
                            class="person"
                            role="checkbox"
                            aria-checked=${on}
                            @click=${() =>
                              setPersons(
                                on
                                  ? ticked.filter((id) => id !== p.entity_id)
                                  : [...ticked, p.entity_id],
                                onlyPresent,
                              )}
                          >
                            <span class="box"
                              >${on ? html`<ha-icon icon="mdi:check"></ha-icon>` : nothing}</span
                            >
                            <span class="grow text">
                              <span class="pname">${p.name}</span>
                              <span class="sub ${p.notify.length ? "" : "warn"}">
                                ${
                                  p.notify.length
                                    ? p.notify
                                        .map((t) => t.replace("notify.mobile_app_", ""))
                                        .join(", ")
                                    : l.t("no_app")
                                }
                              </span>
                            </span>
                          </button>`;
                        })}
                      </div>`
                    : html`<div class="hint">${l.t("no_persons")}</div>`
              }
              ${this._toggle(l.t("only_present"), onlyPresent, (v) => setPersons(ticked, v))}
            `
      }
      ${
        s.targets?.length
          ? html`<div class="also">
              <span class="grow">
                ${l.t("also_to", {
                  targets: s.targets.map((t) => t.replace(/^notify\./, "")).join(", "),
                })}
              </span>
              <button
                class="mini"
                aria-label=${l.t("remove")}
                @click=${() => this._set({ targets: undefined })}
              >
                <ha-icon icon="mdi:close"></ha-icon>
              </button>
            </div>`
          : nothing
      }
    `;
  }

  private _lightFields(): TemplateResult {
    const l = this._l;
    const s = this._sig;
    const columns = columnNames(this.rule);
    const mode = s.color_from !== undefined ? "column" : s.color_from_keyword ? "keyword" : "fixed";
    const keywordColors = this.rule.filter.keywords.rows
      .filter((r) => !!r.color)
      .map((r) => ({ match: String(r.match), color: r.color! }));
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
        <button
          aria-pressed=${mode === "keyword"}
          @click=${() => this._set({ color_from_keyword: true, color_from: undefined })}
        >
          ${l.t("color_keyword")}
        </button>
        <button
          aria-pressed=${mode === "fixed"}
          @click=${() => this._set({ color_from_keyword: undefined, color_from: undefined })}
        >
          ${l.t("color_fixed_pick")}
        </button>
        ${
          mode === "column"
            ? html`<button aria-pressed="true">${l.t("color_column_old")}</button>`
            : nothing
        }
      </div>
      ${
        mode === "column"
          ? html`<select
              .value=${s.color_from ?? ""}
              @change=${(e: Event) => this._set({ color_from: (e.target as HTMLSelectElement).value })}
            >
              ${columns.map((c) => html`<option value=${c} ?selected=${c === s.color_from}>{${c}}</option>`)}
            </select>`
          : nothing
      }
      ${
        mode === "fixed"
          ? html`<laeutwerk-field
              .hass=${this.hass}
              .localize=${l}
              .label=${l.t("color_fixed_pick")}
              .selector=${{ color_rgb: {} }}
              .swatches=${keywordColors.map((k) => ({ label: k.match, color: k.color }))}
              .suggest=${keywordColors[0]?.color ?? ""}
              .value=${s.color ? (colorNameToHex(s.color) ?? s.color) : ""}
              @value-changed=${(e: CustomEvent<{ value: string }>) =>
                this._set({ color: e.detail.value || undefined })}
            ></laeutwerk-field>`
          : nothing
      }
      ${
        keywordColors.length
          ? html`<div class="sublabel">${l.t("keyword_colors")}</div>
              <div class="wrap swatches">
                ${keywordColors.map(
                  ({ match, color }) =>
                    html`<button
                      class="swatch"
                      style="background:${color}"
                      title=${match}
                      aria-label=${`${match} ${color}`}
                      aria-pressed=${mode === "fixed" && s.color?.toLowerCase() === color.toLowerCase()}
                      @click=${() =>
                        this._set({ color, color_from_keyword: undefined, color_from: undefined })}
                    ></button>`,
                )}
              </div>`
          : mode === "keyword"
            ? html`<div class="hint">${l.t("no_keyword_colors")}</div>`
            : nothing
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
      ${this._toggle(
        l.t("restore"),
        s.restore !== false,
        (v) => this._set({ restore: v }),
        "help_restore",
      )}
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
      ${this._text("text", l.t("spoken_text"), true)}
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
    const names = this._variableNames();
    const input = (k: typeof key | typeof pluralKey, fieldLabel: string) =>
      html`<laeutwerk-suggest
        .label=${fieldLabel}
        .multiline=${multiline}
        .variables=${names}
        .value=${String(s[k] ?? "")}
        @value-changed=${(e: CustomEvent<{ value: string }>) => this._set({ [k]: e.detail.value })}
      ></laeutwerk-suggest>`;
    const preview = renderTemplate(s[key], this.sample);
    return html`
      ${input(key, label)} ${input(pluralKey, l.t("plural_variant"))}
      ${
        preview && Object.keys(this.sample).length
          ? html`<div class="preview">
              <ha-icon icon="mdi:eye-outline"></ha-icon><span>${preview}</span>
            </div>`
          : nothing
      }
    `;
  }

  private _variableNames(): string[] {
    return availableVariables(this.rule, this._sig.when !== "now");
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
        ${helpTip(l, "help_limits")}
      </div>
      <hr class="sep" />
      <div class="sublabel head tiprow">${l.t("quiet_times")}${helpTip(l, "help_quiet")}</div>
      <div class="divided">
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
      </div>
      <div class="wrap">
        <button
          class="chip dashed"
          @click=${() => this._set({ quiet: [...quiet, { from: "22:00", to: "08:00", mode: "skip" }] })}
        >
          <ha-icon icon="mdi:plus"></ha-icon>${l.t("add_quiet")}
        </button>
      </div>
      ${
        !quiet.length && this._householdQuiet
          ? html`<div class="hint">
              ${this._householdQuiet
                .map((q) =>
                  l.t("household_quiet", {
                    from: q.from,
                    to: q.to,
                    mode: l.t(q.mode === "defer" ? "quiet_defer" : "quiet_skip"),
                  }),
                )
                .join(" ")}
            </div>`
          : nothing
      }
    `;
  }

  private _toggle(
    label: string,
    value: boolean,
    onChange: (v: boolean) => void,
    help?: StringKey,
  ): TemplateResult {
    return html`<div class="toggle">
      <span class="tiprow">${label}${help ? helpTip(this._l, help) : nothing}</span>
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
        <button class="chip" ?disabled=${this._testState === "…"} @click=${this._test}>
          <ha-icon icon="mdi:play-outline"></ha-icon>${l.t("test")}
        </button>
        <span class="hint grow">${this._testState ?? ""}</span>
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
      .swatch {
        width: 32px;
        height: 32px;
        border-radius: 16px;
        padding: 0;
        box-shadow: 0 0 0 1px var(--lw-border);
      }
      .swatch[aria-pressed="true"] {
        box-shadow:
          0 0 0 2px var(--lw-bg),
          0 0 0 4px var(--lw-accent);
      }
      .head {
        display: flex;
        align-items: center;
        gap: 8px;
        width: 100%;
        min-height: 44px;
        text-align: left;
        padding: 0;
      }
      .head.small {
        font-size: 14px;
        font-weight: 600;
        color: var(--lw-text-2);
      }
      .head .text {
        display: flex;
        flex-direction: column;
        gap: 2px;
        min-width: 0;
      }
      .summary {
        font-size: 12px;
        font-weight: 400;
        color: var(--lw-text-2);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .body {
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      .subsec {
        border-top: 1px solid var(--lw-border);
        padding-top: 4px;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .subsec .body {
        padding-bottom: 8px;
      }
      .also {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 4px 8px 12px;
        border-radius: 12px;
        background: var(--lw-surface-2);
        font-size: 13px;
        overflow-wrap: anywhere;
      }
      .persons {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
      .person {
        display: flex;
        align-items: center;
        gap: 12px;
        min-height: 48px;
        text-align: left;
        width: 100%;
        padding: 0 4px;
      }
      .box {
        width: 24px;
        height: 24px;
        border-radius: 7px;
        border: 2px solid var(--lw-text-2);
        flex-shrink: 0;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        box-sizing: border-box;
      }
      .person[aria-checked="true"] .box {
        background: var(--lw-accent);
        border-color: var(--lw-accent);
        color: var(--lw-on-accent);
      }
      .box ha-icon {
        --mdc-icon-size: 16px;
      }
      .text {
        display: flex;
        flex-direction: column;
        gap: 2px;
        min-width: 0;
      }
      .pname {
        font-size: 14px;
        font-weight: 600;
      }
      .warn {
        color: var(--lw-danger);
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
      .tiprow {
        display: flex;
        align-items: center;
        gap: 4px;
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
