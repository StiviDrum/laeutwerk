/**
 * Dialog of the compact card: confirm "done" for the next task (or another
 * one), snooze it, or create a new rule. Rendered at <body> level so it is not
 * clipped by the one-row grid cell of the compact card.
 */
import { LitElement, css, html, nothing, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import {
  doneLabel,
  doneTasks,
  finishedLine,
  openStatus,
  relativeDay,
  relativeDayTime,
  reminderTitle,
  tasks,
  type Task,
  tooEarlyText,
} from "./format";
import { confirmAction } from "./confirm-dialog";
import type { Localizer } from "./localize";
import { shared, tokens } from "./styles";
import type { HomeAssistant, Rule } from "./types";

function errorText(err: unknown): string {
  if (err && typeof err === "object" && "message" in err) return String(err.message);
  return String(err);
}

export class LaeutwerkTaskDialog extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @property({ attribute: false }) public localize!: Localizer;
  @property({ attribute: false }) public rules: Rule[] = [];
  /** Rule ids the card shows (empty: all). */
  @property({ attribute: false }) public only: string[] = [];
  /** Reminder the dialog asks about (default: the next task). */
  @state() private _selected?: string;
  @state() private _page: "task" | "pick" | "edit" = "task";
  @state() private _editing?: Rule;
  @state() private _busy = false;
  @state() private _error?: string;
  @state() private _laterOpen = false;
  private _onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") this.close();
  };

  public connectedCallback(): void {
    super.connectedCallback();
    document.addEventListener("keydown", this._onKey);
  }

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    document.removeEventListener("keydown", this._onKey);
  }

  public close(): void {
    this.dispatchEvent(new CustomEvent("closed"));
    this.remove();
  }

  private get _l(): Localizer {
    return this.localize;
  }

  private get _tasks(): Task[] {
    return tasks(this.rules, this.only);
  }

  private async _call(
    service: string,
    data: Record<string, unknown>,
    returnResponse = false,
  ): Promise<boolean> {
    if (!this.hass) return false;
    this._busy = true;
    this._error = undefined;
    try {
      const result = await this.hass.callService(
        "laeutwerk",
        service,
        data,
        undefined,
        undefined,
        returnResponse || undefined,
      );
      const early = returnResponse ? tooEarlyText(result) : undefined;
      if (early) {
        this._error = early;
        return false;
      }
      return true;
    } catch (err) {
      this._error = this._l.t("failed", { error: errorText(err) });
      return false;
    } finally {
      this._busy = false;
    }
  }

  private _ask(task: Task, text: string, confirm: string, icon: string): Promise<boolean> {
    return confirmAction({
      title: reminderTitle(task.reminder),
      text,
      confirm,
      cancel: this._l.t("cancel"),
      icon,
      dark: this.hasAttribute("dark"),
    });
  }

  private async _done(task: Task): Promise<void> {
    const l = this._l;
    const text = task.open ? l.t("confirm_done") : l.t("confirm_done_early");
    if (!(await this._ask(task, text, doneLabel(task.rule, l), "mdi:check"))) return;
    // Also planned tasks can be done ahead of time (asked above).
    const ok = await this._call(
      "acknowledge",
      {
        rule: task.rule.id,
        reminder_id: task.reminder.id,
      },
      true,
    );
    if (ok) this.close();
  }

  private async _reopen(task: Task): Promise<void> {
    const l = this._l;
    if (!(await this._ask(task, l.t("confirm_reopen"), l.t("reopen"), "mdi:undo"))) return;
    const ok = await this._call("reopen", { reminder_id: task.reminder.id });
    if (ok) this._selected = undefined;
  }

  private async _later(task: Task, choice: "1h" | "3h" | "morning"): Promise<void> {
    const when = choice === "morning" ? { until: "07:00" } : { duration: choice };
    const ok = await this._call("snooze", {
      rule: task.rule.id,
      reminder_id: task.reminder.id,
      ...when,
    });
    if (ok) this.close();
  }

  protected render(): TemplateResult {
    const l = this._l;
    let body: TemplateResult;
    if (this._page === "pick") {
      body = html`<laeutwerk-template-picker
        .hass=${this.hass}
        .localize=${l}
        @pick=${(e: CustomEvent<{ rule: Rule }>) => {
          this._editing = e.detail.rule;
          this._page = "edit";
        }}
        @imported=${() => this.close()}
        @cancel=${() => (this._page = "task")}
      ></laeutwerk-template-picker>`;
    } else if (this._page === "edit" && this._editing) {
      body = html`<laeutwerk-rule-editor
        .hass=${this.hass}
        .localize=${l}
        .rule=${this._editing}
        @saved=${() => this.close()}
        @deleted=${() => this.close()}
        @cancel=${() => (this._page = "task")}
      ></laeutwerk-rule-editor>`;
    } else {
      body = this._taskPage();
    }
    return html`<div class="backdrop" @click=${() => this.close()}></div>
      <div class="sheet" role="dialog" aria-modal="true" aria-label=${l.t("title")}>
        <div class="grabber"></div>
        ${body}
      </div>`;
  }

  private _taskPage(): TemplateResult {
    const l = this._l;
    const all = this._tasks;
    const done = doneTasks(this.rules, new Date(), this.only);
    const task = all.find((t) => t.reminder.id === this._selected) ?? all[0];
    const others = all.filter((t) => t !== task);
    const tz = this.hass?.config?.time_zone;
    const now = new Date();
    const admin = !!this.hass?.user?.is_admin;
    return html`
      ${
        task
          ? html`<div class="question">
              <div class="row">
                ${this._icon(task.rule)}
                <div class="grow text">
                  <div class="title">${reminderTitle(task.reminder)}</div>
                  <div class="sub">
                    ${task.rule.name} ·
                    ${
                      task.open
                        ? openStatus(task.reminder, now, l, tz)
                        : task.reminder.next_reminder_at
                          ? l.t("reminder_at", {
                              when: relativeDayTime(task.reminder.next_reminder_at, now, l, tz),
                            })
                          : relativeDay(task.reminder.start, now, l, tz)
                    }
                  </div>
                </div>
              </div>
              ${task.open ? nothing : html`<div class="ask">${l.t("not_due_yet")}</div>`}
              ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
              ${
                this._laterOpen && task.open
                  ? html`<div class="later">
                      ${(
                        [
                          ["1h", "later_1h"],
                          ["3h", "later_3h"],
                          ["morning", "later_morning"],
                        ] as const
                      ).map(
                        ([choice, key]) =>
                          html`<button
                            class="pill outline"
                            ?disabled=${this._busy}
                            @click=${() => this._later(task, choice)}
                          >
                            ${l.t(key)}
                          </button>`,
                      )}
                    </div>`
                  : nothing
              }
              <div class="actions">
                <button class="pill outline" @click=${() => this.close()}>${l.t("cancel")}</button>
                ${
                  task.open
                    ? html`<button
                        class="pill outline"
                        aria-expanded=${this._laterOpen}
                        @click=${() => (this._laterOpen = !this._laterOpen)}
                      >
                        ${l.t("later")}
                      </button>`
                    : nothing
                }
                <button
                  class="pill primary"
                  ?disabled=${this._busy}
                  aria-label=${doneLabel(task.rule, l)}
                  @click=${() => this._done(task)}
                >
                  ${this._busy ? "…" : html`<ha-icon icon="mdi:check"></ha-icon>`}
                </button>
              </div>
            </div>`
          : html`<div class="hint">${l.t("no_tasks")}</div>`
      }
      ${
        others.length
          ? html`<div class="separator">${l.t("more_tasks")}<span class="line"></span></div>
              <div class="divided">
                ${others.map(
                  (t) =>
                    html`<button
                      class="row item"
                      @click=${() => {
                        this._selected = t.reminder.id;
                        this._laterOpen = false;
                        this._error = undefined;
                      }}
                    >
                      ${this._icon(t.rule)}
                      <span class="grow text">
                        <span class="name ${t.open ? "" : "dim"}"
                          >${reminderTitle(t.reminder)}</span
                        >
                      </span>
                      ${t.open ? html`<span class="when">${l.t("open_tasks")}</span>` : nothing}
                    </button>`,
                )}
              </div>`
          : nothing
      }
      ${
        done.length
          ? html`<div class="separator">${l.t("done_already")}<span class="line"></span></div>
              <div class="divided">
                ${done.map(
                  (t) =>
                    html`<button
                      class="row item"
                      @click=${() => {
                        this._error = undefined;
                        void this._reopen(t);
                      }}
                    >
                      ${this._icon(t.rule)}
                      <span class="grow text">
                        <span class="name struck">${reminderTitle(t.reminder)}</span>
                        <span class="sub">${finishedLine(t.reminder, now, l, tz)}</span>
                      </span>
                      <ha-icon class="undo" icon="mdi:undo"></ha-icon>
                    </button>`,
                )}
              </div>`
          : nothing
      }
      ${
        admin
          ? html`<div class="separator">${l.t("section_rules")}<span class="line"></span></div>
              <div class="divided">
                ${this.rules.map(
                  (rule) =>
                    html`<button
                      class="row item"
                      @click=${() => {
                        this._editing = rule;
                        this._page = "edit";
                      }}
                    >
                      ${this._icon(rule)}
                      <span class="grow text">
                        <span class="name">${rule.name}</span>
                        ${rule.enabled ? nothing : html`<span class="sub">${l.t("rule_off")}</span>`}
                      </span>
                      <ha-icon class="undo" icon="mdi:pencil-outline"></ha-icon>
                    </button>`,
                )}
              </div>
              <button class="chip dashed new" @click=${() => (this._page = "pick")}>
                <ha-icon icon="mdi:plus"></ha-icon>${l.t("new_rule")}
              </button>`
          : nothing
      }
    `;
  }

  private _icon(rule: Rule): TemplateResult {
    const color = rule.color ?? "var(--lw-text-2)";
    return html`<span
      class="icon small"
      style="background: color-mix(in srgb, ${color} 22%, transparent); color: ${color}"
    >
      <ha-icon .icon=${rule.icon || "mdi:bell-ring-outline"}></ha-icon>
    </span>`;
  }

  static styles = [
    tokens,
    shared,
    css`
      :host {
        position: fixed;
        inset: 0;
        z-index: 1000;
        display: flex;
        align-items: flex-end;
        justify-content: center;
      }
      .backdrop {
        position: absolute;
        inset: 0;
        background: rgba(0, 0, 0, 0.5);
      }
      .sheet {
        position: relative;
        width: 100%;
        max-width: 480px;
        max-height: 90vh;
        overflow-y: auto;
        box-sizing: border-box;
        padding: 10px 16px calc(16px + env(safe-area-inset-bottom));
        border-radius: 28px 28px 0 0;
        background: var(--lw-bg);
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      @media (min-width: 600px) {
        :host {
          align-items: center;
        }
        .sheet {
          border-radius: 28px;
        }
      }
      .grabber {
        width: 40px;
        height: 4px;
        border-radius: 2px;
        background: var(--lw-border);
        align-self: center;
      }
      .question {
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      .text {
        display: flex;
        flex-direction: column;
        gap: 2px;
        min-width: 0;
      }
      .title {
        font-size: 17px;
        font-weight: 700;
      }
      .ask {
        font-size: 15px;
      }
      .later {
        display: flex;
        gap: 6px;
      }
      .later .pill {
        flex: 1;
        min-width: 0;
        padding: 0 8px;
        font-size: 13px;
      }
      .item {
        width: 100%;
        text-align: left;
        min-height: 48px;
      }
      .dim {
        color: var(--lw-text-2);
        font-weight: 500;
      }
      .when {
        font-size: 13px;
        color: var(--lw-text-2);
        white-space: nowrap;
      }
      .struck {
        text-decoration: line-through;
        color: var(--lw-text-2);
        font-weight: 500;
      }
      .undo {
        color: var(--lw-text-2);
      }
      .new {
        align-self: flex-start;
      }
      .actions ha-icon {
        --mdc-icon-size: 22px;
      }
    `,
  ];
}
