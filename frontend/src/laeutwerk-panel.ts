/**
 * laeutwerk-panel: sidebar panel with tabs: overview, rules (list + pipeline
 * editor), history and health (UI rework).
 */
import { LitElement, css, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import { relativeDay } from "./format";
import {
  fetchPreview90,
  healthOf,
  matchPayload,
  worst,
  type HealthItem,
  type Preview90,
} from "./health";
import { localizer, type Localizer, type StringKey } from "./localize";
import {
  PANEL_TABS,
  filterRules,
  isNarrow,
  panelPath,
  parsePanelPath,
  type PanelRoute,
  type PanelTab,
} from "./panel-logic";
import "./laeutwerk-card";
import { LaeutwerkHistory } from "./panel-history";
import { LaeutwerkOverview } from "./panel-overview";
import { applyRuleEvent } from "./rule-events";
import { shared, tokens } from "./styles";
import type { HomeAssistant, Rule, RuleEvent } from "./types";
import { defineElements } from "./register";
import { CARD_VERSION } from "./version";

const TAB_KEYS: Record<PanelTab, StringKey> = {
  overview: "tab_overview",
  rules: "tab_rules",
  history: "tab_history",
  health: "tab_health",
};

export class LaeutwerkPanel extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @property({ type: Boolean }) public narrow = false;
  @property({ attribute: false }) public route?: { prefix: string; path: string };
  @property({ attribute: false }) public panel?: unknown;
  @state() private _rules?: Rule[];
  @state() private _error?: string;
  @state() private _query = "";
  @state() private _width = 0;
  @state() private _picking = false;
  @state() private _listOpen = (() => {
    try {
      return window.localStorage.getItem("laeutwerk-list-open") === "1";
    } catch {
      return false;
    }
  })();
  @state() private _health90: Record<string, Preview90 | undefined> = {};
  private _healthLoaded = false;
  @state() private _toast?: { text: string; undo?: () => void };
  @state() private _tool?: "export" | "import";
  @state() private _toolText = "";
  @state() private _toolMsg?: { text: string; error?: boolean };
  /** Import text that passed the dry run. */
  @state() private _checked = "";
  private _undoable?: { previous?: Rule; saved?: Rule };
  private _toastTimer?: number;
  @state() private _editorsReady = false;
  /** Snapshot handed to the editor (never the live rule: it would reset the editor). */
  @state() private _editing?: { key: string; rule: Rule };
  private _unsub?: Promise<() => void>;
  private _ro?: ResizeObserver;
  private _editorsLoading = false;
  private _newPath?: string;

  private get _l(): Localizer {
    return localizer(this.hass?.locale?.language ?? this.hass?.language);
  }

  private get _route(): PanelRoute {
    return parsePanelPath(this.route?.path);
  }

  private get _isNarrow(): boolean {
    return isNarrow(this.narrow, this._width);
  }

  public connectedCallback(): void {
    super.connectedCallback();
    this._ro = new ResizeObserver(() => (this._width = this.clientWidth));
    this._ro.observe(this);
    if (this.hass && !this._unsub) this._subscribe();
  }

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    this._ro?.disconnect();
    const unsub = this._unsub;
    this._unsub = undefined;
    unsub?.then((fn) => fn()).catch(() => undefined);
  }

  private _subscribe(): void {
    if (!this.hass?.connection) return;
    const unsub = this.hass.connection.subscribeMessage<RuleEvent>(
      (msg) => {
        this._rules = applyRuleEvent(this._rules, msg);
        this._error = undefined;
      },
      { type: "laeutwerk/rules/subscribe" },
    );
    this._unsub = unsub;
    unsub.catch((err) => {
      if (this._unsub !== unsub) return;
      this._unsub = undefined;
      this._error = String((err as { message?: string })?.message ?? err);
    });
  }

  protected willUpdate(changed: PropertyValues): void {
    if (changed.has("hass") && this.hass) {
      this.toggleAttribute("dark", !!this.hass.themes?.darkMode);
      if (!this._unsub && this.isConnected) this._subscribe();
    }
    const { tab, ruleId } = this._route;
    // "/rules/new" (from the card): open the template picker once per visit.
    if (tab === "rules" && ruleId === "new") {
      if (this._newPath !== this.route?.path) {
        this._newPath = this.route?.path;
        this._editing = undefined;
        this._picking = true;
      }
    } else this._newPath = undefined;
    if (
      tab === "rules" &&
      ruleId &&
      ruleId !== "new" &&
      this._rules &&
      this._editing?.key !== ruleId
    ) {
      const rule = this._rules.find((r) => r.id === ruleId);
      if (rule) this._editing = { key: ruleId, rule: structuredClone(rule) };
    } else if (!ruleId && this._editing && !this._editing.key.startsWith("new:")) {
      this._editing = undefined;
    }
    if (tab === "health" && this._rules && !this._healthLoaded) void this._loadHealth();
    if (tab !== "health") this._healthLoaded = false;
    if (tab === "rules" && !this._editorsReady && !this._editorsLoading) {
      this._editorsLoading = true;
      import("./editors")
        .then((m) => m.ready)
        .then(() => (this._editorsReady = true))
        .catch((e) => {
          this._editorsLoading = false;
          this._error = String(e);
        });
    }
  }

  private async _loadHealth(): Promise<void> {
    const hass = this.hass;
    if (!hass || !this._rules) return;
    this._healthLoaded = true;
    const next: Record<string, Preview90 | undefined> = {};
    await Promise.all(
      this._rules
        .filter((r) => r.id && r.sources?.length && !r.start_triggers?.length && !r.interval)
        .map(async (r) => {
          try {
            next[r.id!] = await fetchPreview90(hass, matchPayload(r));
          } catch {
            /* event based checks are skipped for this rule */
          }
        }),
    );
    this._health90 = next;
  }

  private _healthText(item: HealthItem): string {
    return this._l.t(`health_${item.code}` as StringKey, item.params);
  }

  private _renderHealth(): TemplateResult {
    const l = this._l;
    if (this._error) return html`<div class="message error">${this._error}</div>`;
    if (!this.hass || !this._rules) return html`<div class="message">${l.t("loading")}</div>`;
    const hass = this.hass;
    const rows = this._rules
      .map((rule) => ({ rule, items: healthOf(rule, hass, this._health90[rule.id ?? ""]) }))
      .filter((x) => x.items.length);
    return html`<div class="healthtab">
      <h2>${l.t("health_title")}</h2>
      ${rows.length === 0 ? html`<div class="message">${l.t("health_none")}</div>` : nothing}
      ${rows.map(
        ({ rule, items }) =>
          html`<section class="hgroup">
            <button class="hrule" @click=${() => this._select(rule)}>
              <span class="dot" style=${rule.color ? `background:${rule.color}` : ""}>
                <ha-icon icon=${rule.icon || "mdi:bell-outline"}></ha-icon>
              </span>
              <span class="name">${rule.name}</span>
            </button>
            ${items.map(
              (item) =>
                html`<button class="hitem h-${item.severity}" @click=${() => this._select(rule)}>
                  <ha-icon
                    icon=${item.severity === "info" ? "mdi:information-outline" : "mdi:alert-circle-outline"}
                  ></ha-icon>
                  ${this._healthText(item)}
                </button>`,
            )}
          </section>`,
      )}
    </div>`;
  }

  private _go(tab: PanelTab, ruleId = ""): void {
    const prefix = this.route?.prefix ?? "/laeutwerk";
    history.pushState(null, "", `${prefix}${panelPath(tab, ruleId)}`);
    window.dispatchEvent(new CustomEvent("location-changed"));
    this.requestUpdate();
  }

  private _showToast(text: string, undo?: () => void): void {
    this._toast = { text, undo };
    window.clearTimeout(this._toastTimer);
    this._toastTimer = window.setTimeout(() => (this._toast = undefined), undo ? 10000 : 5000);
  }

  /** Revert the last save / delete (restore the previous rule). */
  private async _revert(u: { previous?: Rule; saved?: Rule }): Promise<void> {
    this._toast = undefined;
    const strip = (r: Rule): Rule => {
      const copy = JSON.parse(JSON.stringify(r)) as Rule;
      delete copy.status;
      return copy;
    };
    try {
      if (u.previous && u.saved) {
        await this.hass?.callWS({
          type: "laeutwerk/rules/update",
          rule_id: u.previous.id,
          rule: strip(u.previous),
        });
      } else if (u.saved) {
        await this.hass?.callWS({ type: "laeutwerk/rules/delete", rule_id: u.saved.id });
      } else if (u.previous) {
        await this.hass?.callWS({ type: "laeutwerk/rules/create", rule: strip(u.previous) });
      }
    } catch (err) {
      this._showToast(this._errText(err));
    }
  }

  private async _openTool(tool: "export" | "import"): Promise<void> {
    this._picking = false;
    this._tool = tool;
    this._toolMsg = undefined;
    this._toolText = "";
    this._checked = "";
    if (tool === "export") {
      try {
        const res = await this.hass?.callWS<{ yaml: string }>({ type: "laeutwerk/rules/export" });
        this._toolText = res?.yaml ?? "";
      } catch (err) {
        this._toolMsg = { text: this._errText(err), error: true };
      }
    }
  }

  private _errText(err: unknown): string {
    const msg = err && typeof err === "object" && "message" in err ? err.message : err;
    return this._l.t("failed", { error: String(msg) });
  }

  private async _checkImport(): Promise<void> {
    if (!this._toolText.trim()) return;
    this._toolMsg = undefined;
    this._checked = "";
    const text = this._toolText;
    try {
      const res = await this.hass?.callWS<{
        rules: { id: string; name: string; new_id?: string }[];
        errors?: unknown[];
      }>({ type: "laeutwerk/rules/import", yaml: text, dry_run: true });
      if (res?.errors?.length) {
        this._toolMsg = { text: res.errors.map(String).join("\n"), error: true };
        return;
      }
      const list = (res?.rules ?? [])
        .map((r) => (r.new_id && r.new_id !== r.id ? `${r.name} (${r.id} → ${r.new_id})` : r.name))
        .join(", ");
      this._toolMsg = {
        text: `${this._l.t("import_result", { n: res?.rules.length ?? 0 })} ${list}`,
      };
      this._checked = text;
    } catch (err) {
      this._toolMsg = { text: this._errText(err), error: true };
    }
  }

  private async _runImport(): Promise<void> {
    if (!this._toolText.trim() || this._checked !== this._toolText) return;
    this._toolMsg = undefined;
    try {
      const res = await this.hass?.callWS<{ rules: Rule[] }>({
        type: "laeutwerk/rules/import",
        yaml: this._toolText,
      });
      this._toolMsg = { text: `✓ ${this._l.t("import_result", { n: res?.rules.length ?? 0 })}` };
      this._checked = "";
    } catch (err) {
      this._toolMsg = { text: this._errText(err), error: true };
    }
  }

  private _download(): void {
    const url = URL.createObjectURL(new Blob([this._toolText], { type: "text/yaml" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "laeutwerk-rules.yaml";
    a.click();
    URL.revokeObjectURL(url);
  }

  private _renderTool(): TemplateResult {
    const l = this._l;
    const exporting = this._tool === "export";
    return html`<div class="tool">
      <div class="ename">${exporting ? l.t("export_all") : l.t("import_yaml")}</div>
      <div class="hint">${exporting ? l.t("export_hint") : l.t("import_hint")}</div>
      <textarea
        spellcheck="false"
        ?readonly=${exporting}
        .value=${this._toolText}
        @input=${(e: Event) => {
          this._toolText = (e.target as HTMLTextAreaElement).value;
          this._checked = "";
        }}
      ></textarea>
      ${
        this._toolMsg
          ? html`<div class=${this._toolMsg.error ? "message error" : "message"}>
              ${this._toolMsg.text}
            </div>`
          : nothing
      }
      <div class="toolbtns">
        ${
          exporting
            ? html`<button
                  class="pill outline"
                  @click=${() => void navigator.clipboard?.writeText(this._toolText)}
                >
                  ${l.t("export_copy")}
                </button>
                <button class="pill primary" @click=${this._download}>
                  ${l.t("export_download")}
                </button>`
            : html`<button
                  class="pill outline"
                  ?disabled=${!this._toolText.trim()}
                  @click=${this._checkImport}
                >
                  ${l.t("import_check")}
                </button>
                <button
                  class="pill primary"
                  ?disabled=${!this._checked || this._checked !== this._toolText}
                  @click=${this._runImport}
                >
                  ${l.t("import_button")}
                </button>`
        }
        <button class="pill outline" @click=${() => (this._tool = undefined)}>
          ${l.t("close")}
        </button>
      </div>
    </div>`;
  }

  private _closeEditor(): void {
    this._editing = undefined;
    this._go("rules");
  }

  // --- Render ---------------------------------------------------------------

  protected render(): TemplateResult {
    const l = this._l;
    const { tab } = this._route;
    const rules = this._route.tab === "rules";
    const inDetail = rules && this._isNarrow && (!!this._editing || this._picking);
    return html`
      <header class="bar">
        ${
          inDetail
            ? html`<button class="icon-btn" aria-label=${l.t("back")} @click=${() => this._back()}>
                <ha-icon icon="mdi:arrow-left"></ha-icon>
              </button>`
            : html`<ha-menu-button .hass=${this.hass} .narrow=${this.narrow}></ha-menu-button>`
        }
        <span class="title">Läutwerk</span>
        <nav class="tabs" role="tablist">
          ${PANEL_TABS.map(
            (id) =>
              html`<button
                class="tab"
                role="tab"
                aria-selected=${id === tab}
                @click=${() => this._go(id)}
              >
                ${l.t(TAB_KEYS[id])}
              </button>`,
          )}
        </nav>
      </header>
      <main>
        ${
          tab === "rules"
            ? this._renderRules()
            : tab === "health"
              ? this._renderHealth()
              : tab === "history"
                ? this._renderHistory()
                : this._renderOverview()
        }
      </main>
      ${
        this._toast
          ? html`<div class="toast" role="status">
              ${this._toast.text}${
                this._toast.undo
                  ? html`<button class="toast-undo" @click=${this._toast.undo}>
                      ${l.t("undo")}
                    </button>`
                  : nothing
              }
            </div>`
          : nothing
      }
    `;
  }

  private _back(): void {
    if (this._picking) this._picking = false;
    else this._closeEditor();
  }

  private _renderOverview(): TemplateResult {
    if (!this.hass || !this._rules) return html`<div class="message">${this._l.t("loading")}</div>`;
    return html`<laeutwerk-overview
      .hass=${this.hass}
      .localize=${this._l}
      .rules=${this._rules}
      @navigate=${(e: CustomEvent<PanelTab>) => this._go(e.detail)}
    ></laeutwerk-overview>`;
  }

  private _renderHistory(): TemplateResult {
    if (!this.hass || !this._rules) return html`<div class="message">${this._l.t("loading")}</div>`;
    return html`<laeutwerk-history
      .hass=${this.hass}
      .localize=${this._l}
      .rules=${this._rules}
    ></laeutwerk-history>`;
  }

  private _renderRules(): TemplateResult {
    const l = this._l;
    if (this._error) return html`<div class="message error">${this._error}</div>`;
    if (!this.hass || !this._rules) return html`<div class="message">${l.t("loading")}</div>`;
    const detail = !!this._editing || this._picking;
    const narrow = this._isNarrow;
    const rail = !narrow && detail && !this._listOpen;
    return html`<div class="split ${narrow ? "narrow" : ""} ${rail ? "rail" : ""}">
      ${narrow && detail ? nothing : rail ? this._renderRail() : this._renderList()}
      ${!narrow || detail ? html`<section class="detail">${this._renderDetail()}</section>` : nothing}
    </div>`;
  }

  private _setListOpen(open: boolean): void {
    this._listOpen = open;
    try {
      window.localStorage.setItem("laeutwerk-list-open", open ? "1" : "0");
    } catch {
      /* storage blocked */
    }
  }

  private _renderRail(): TemplateResult {
    const l = this._l;
    const rules = this._rules ?? [];
    return html`<aside class="rail-list">
      <button
        class="icon-btn"
        aria-label=${l.t("show_list")}
        title=${l.t("show_list")}
        @click=${() => this._setListOpen(true)}
      >
        <ha-icon icon="mdi:chevron-right"></ha-icon>
      </button>
      ${rules.map(
        (rule) =>
          html`<button
            class="dot railbtn ${rule.id === this._route.ruleId ? "sel" : ""}"
            title=${rule.name}
            aria-label=${rule.name}
            style=${rule.color ? `background:${rule.color}` : ""}
            @click=${() => this._select(rule)}
          >
            <ha-icon icon=${rule.icon || "mdi:bell-outline"}></ha-icon>
          </button>`,
      )}
    </aside>`;
  }

  private _renderList(): TemplateResult {
    const l = this._l;
    const rules = filterRules(this._rules ?? [], this._query);
    const now = new Date();
    return html`<aside class="list">
      <div class="list-head">
        <input
          type="search"
          .value=${this._query}
          placeholder=${l.t("search")}
          aria-label=${l.t("search")}
          @input=${(e: Event) => (this._query = (e.target as HTMLInputElement).value)}
        />
        <button class="primary" @click=${() => ((this._tool = undefined), (this._picking = true))}>
          <ha-icon icon="mdi:plus"></ha-icon>${l.t("new_rule")}
        </button>
        <button
          class="icon-btn"
          aria-label=${l.t("export_all")}
          title=${l.t("export_all")}
          @click=${() => void this._openTool("export")}
        >
          <ha-icon icon="mdi:export"></ha-icon>
        </button>
        <button
          class="icon-btn"
          aria-label=${l.t("import_all")}
          title=${l.t("import_all")}
          @click=${() => void this._openTool("import")}
        >
          <ha-icon icon="mdi:import"></ha-icon>
        </button>
        ${
          this._editing && !this._isNarrow
            ? html`<button
                class="icon-btn"
                aria-label=${l.t("hide_list")}
                @click=${() => this._setListOpen(false)}
              >
                <ha-icon icon="mdi:chevron-left"></ha-icon>
              </button>`
            : nothing
        }
      </div>
      ${rules.length === 0 ? html`<div class="message">${l.t("no_rules")}</div>` : nothing}
      ${rules.map((rule) => {
        const status = this._status(rule, now);
        return html`<div class="row ${rule.id === this._route.ruleId ? "sel" : ""}">
          <button class="pick" data-rule=${rule.id ?? ""} @click=${() => this._select(rule)}>
            <span class="dot" style=${rule.color ? `background:${rule.color}` : ""}>
              <ha-icon icon=${rule.icon || "mdi:bell-outline"}></ha-icon>
            </span>
            <span class="text">
              <span class="name">${rule.name}</span>
              <span class="sub">${status}</span>
            </span>
            ${(() => {
              const w = worst(healthOf(rule, this.hass));
              return w === "error" || w === "warning"
                ? html`<span
                    class="hbadge h-${w}"
                    title=${l.t(`health_badge_${w}` as StringKey)}
                  ></span>`
                : nothing;
            })()}
          </button>
          <button
            class="switch"
            role="switch"
            aria-checked=${rule.enabled}
            aria-label=${rule.name}
            @click=${() => this._toggle(rule)}
          >
            <span></span>
          </button>
        </div>`;
      })}
    </aside>`;
  }

  private _status(rule: Rule, now: Date): string {
    const l = this._l;
    if (Object.keys(rule.status?.errors ?? {}).length) return l.t("rule_error");
    if (!rule.enabled) return l.t("rule_off");
    if (rule.status?.active === false) return l.t("rule_inactive");
    const next = rule.status?.next_event;
    if (!next) return "";
    return `${next.titles.join(" + ")} · ${relativeDay(next.start, now, l, this.hass?.config?.time_zone)}`;
  }

  private _select(rule: Rule): void {
    this._picking = false;
    this._go("rules", rule.id ?? "");
  }

  private _toggle(rule: Rule): void {
    void this.hass
      ?.callService("laeutwerk", rule.enabled ? "disable" : "enable", { rule: rule.id })
      .catch(() => undefined);
  }

  private _renderDetail(): TemplateResult {
    const l = this._l;
    if (!this._editorsReady) return html`<div class="message">${l.t("loading")}</div>`;
    if (this._tool) return this._renderTool();
    if (this._picking) {
      return html`<laeutwerk-template-picker
        .hass=${this.hass}
        .localize=${l}
        @pick=${(e: CustomEvent<{ rule: Rule }>) => {
          this._picking = false;
          this._editing = { key: `new:${Date.now()}`, rule: e.detail.rule };
        }}
        @imported=${() => (this._picking = false)}
        @cancel=${() => (this._picking = false)}
      ></laeutwerk-template-picker>`;
    }
    if (!this._editing) return html`<div class="message">${l.t("panel_pick")}</div>`;
    return html`<laeutwerk-rule-editor
      .hass=${this.hass}
      .localize=${l}
      .rule=${this._editing.rule}
      layout="pipeline"
      @undoable=${(e: CustomEvent<{ previous?: Rule; saved?: Rule }>) =>
        (this._undoable = e.detail)}
      @saved=${() => {
        const u = this._undoable;
        this._closeEditor();
        this._showToast(l.t("saved_toast"), u && (() => void this._revert(u)));
      }}
      @duplicated=${(e: CustomEvent<Rule>) => {
        this._editing = undefined;
        this._go("rules", e.detail.id ?? "");
      }}
      @deleted=${() => {
        const u = this._undoable;
        this._closeEditor();
        this._showToast(l.t("undo_toast_deleted"), u && (() => void this._revert(u)));
      }}
      @cancel=${() => this._closeEditor()}
    ></laeutwerk-rule-editor>`;
  }

  static styles = [
    tokens,
    shared,
    css`
      .healthtab {
        max-width: 760px;
        margin: 0 auto;
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      .hgroup {
        display: flex;
        flex-direction: column;
        gap: 4px;
        padding: 8px;
        border: 1px solid var(--lw-border);
        border-radius: 18px;
      }
      .hrule,
      .hitem {
        display: flex;
        align-items: center;
        gap: 10px;
        min-height: 44px;
        padding: 0 8px;
        border: none;
        background: none;
        color: var(--lw-text);
        font: inherit;
        text-align: left;
        cursor: pointer;
        border-radius: 12px;
      }
      .hrule {
        font-weight: 600;
      }
      .hitem {
        font-size: 14px;
      }
      .hitem.h-error ha-icon,
      .hbadge.h-error {
        color: var(--lw-danger);
        background: var(--lw-danger);
      }
      .hitem.h-warning ha-icon {
        color: #ffb300;
      }
      .hitem.h-info ha-icon {
        color: var(--lw-text-2);
      }
      .hitem ha-icon {
        background: none !important;
      }
      .hbadge {
        width: 10px;
        height: 10px;
        border-radius: 5px;
        flex: none;
        margin-right: 8px;
      }
      .hbadge.h-warning {
        background: #ffb300;
      }
    `,
    css`
      :host {
        display: flex;
        flex-direction: column;
        min-height: 100vh;
        background: var(--primary-background-color, #0b0b0d);
        box-sizing: border-box;
      }
      .bar {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        min-height: 56px;
        padding: 4px 12px;
        background: var(--app-header-background-color, var(--lw-bg));
        color: var(--app-header-text-color, var(--lw-text));
        border-bottom: 1px solid var(--lw-border);
        position: sticky;
        top: 0;
        z-index: 2;
      }
      .title {
        font-size: 20px;
        font-weight: 600;
        margin-right: 8px;
      }
      .icon-btn {
        width: 44px;
        height: 44px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 50%;
      }
      .tabs {
        display: flex;
        gap: 4px;
        overflow-x: auto;
      }
      .tab {
        min-height: 44px;
        padding: 0 16px;
        border-radius: 22px;
        color: var(--lw-text-2);
        font-weight: 500;
      }
      .tab[aria-selected="true"] {
        background: var(--lw-surface-2);
        color: var(--lw-text);
      }
      main {
        flex: 1;
        padding: 16px;
        box-sizing: border-box;
        min-width: 0;
      }
      .overview {
        max-width: 720px;
        margin: 0 auto;
      }
      .split {
        display: grid;
        grid-template-columns: 340px minmax(0, 1fr);
        gap: 16px;
        align-items: start;
      }
      .split.rail {
        grid-template-columns: 56px minmax(0, 1fr);
      }
      .rail-list {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 8px;
        padding: 8px 0;
      }
      .railbtn {
        width: 44px;
        height: 44px;
        border-radius: 22px;
        border: 2px solid transparent;
        background: var(--lw-surface-2);
        color: var(--lw-text);
        cursor: pointer;
      }
      .railbtn.sel {
        border-color: var(--lw-accent);
      }
      .split.narrow {
        grid-template-columns: minmax(0, 1fr);
      }
      .list,
      .detail {
        background: var(--lw-bg);
        border: 1px solid var(--lw-border);
        border-radius: var(--lw-radius-card);
        padding: 12px;
        min-width: 0;
        box-sizing: border-box;
      }
      .list-head {
        display: flex;
        gap: 8px;
        margin-bottom: 8px;
      }
      input[type="search"] {
        flex: 1;
        min-width: 0;
        min-height: 44px;
        box-sizing: border-box;
        border-radius: 22px;
        border: 1px solid var(--lw-border);
        background: var(--lw-surface);
        color: inherit;
        padding: 0 16px;
        font: inherit;
      }
      .primary {
        min-height: 44px;
        padding: 0 14px;
        border-radius: 22px;
        background: var(--lw-accent);
        color: var(--lw-on-accent);
        display: inline-flex;
        align-items: center;
        gap: 4px;
        font-weight: 600;
        white-space: nowrap;
      }
      .row {
        display: flex;
        align-items: center;
        gap: 8px;
        border-radius: 18px;
      }
      .row.sel {
        background: var(--lw-surface-2);
      }
      .pick {
        flex: 1;
        min-width: 0;
        min-height: 52px;
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 4px 8px;
        text-align: left;
      }
      .dot {
        flex: none;
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background: var(--lw-surface-2);
        display: inline-flex;
        align-items: center;
        justify-content: center;
      }
      .text {
        display: flex;
        flex-direction: column;
        min-width: 0;
      }
      .name,
      .sub {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .sub {
        color: var(--lw-text-2);
        font-size: 13px;
      }
      .row .switch {
        margin-right: 8px;
      }
      .toast {
        position: fixed;
        left: 50%;
        bottom: 24px;
        transform: translateX(-50%);
        max-width: calc(100vw - 32px);
        padding: 12px 18px;
        border-radius: 22px;
        background: var(--lw-accent);
        color: var(--lw-on-accent);
        z-index: 10;
      }
      .toast-undo {
        margin-left: 12px;
        min-height: 36px;
        padding: 0 12px;
        border-radius: 18px;
        background: transparent;
        color: inherit;
        font-weight: 600;
        text-decoration: underline;
      }
      .tool {
        display: flex;
        flex-direction: column;
        gap: 12px;
        max-width: 720px;
      }
      .tool textarea {
        min-height: 280px;
        font-family: monospace;
        font-size: 13px;
      }
      .toolbtns {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }
      .message {
        white-space: pre-line;
        padding: 24px 12px;
        color: var(--lw-text-2);
        text-align: center;
      }
      .message.error {
        color: var(--lw-danger);
      }
    `,
  ];
}

defineElements([
  ["laeutwerk-panel", LaeutwerkPanel],
  ["laeutwerk-overview", LaeutwerkOverview],
  ["laeutwerk-history", LaeutwerkHistory],
]);
console.info(`%c LÄUTWERK-PANEL %c ${CARD_VERSION} `, "background:#222;color:#fff", "");
