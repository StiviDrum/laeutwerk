/** Rendering of the event log shared by the history tab and the rule editor. */
import { css, html, type TemplateResult } from "lit";
import { groupByDay } from "./event-log";
import { formatDate, formatTime } from "./format";
import type { Localizer, StringKey } from "./localize";
import type { HomeAssistant, LogEvent } from "./types";

export interface EventQuery {
  rule_id?: string;
  kinds?: string[];
  since?: string;
  limit?: number;
}

export async function fetchEvents(hass: HomeAssistant, query: EventQuery): Promise<LogEvent[]> {
  const msg: Record<string, unknown> = { type: "laeutwerk/events" };
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && !(Array.isArray(v) && !v.length)) msg[k] = v;
  }
  const res = await hass.callWS<{ events: LogEvent[] }>(msg);
  return res?.events ?? [];
}

const KIND_ICONS: Record<string, string> = {
  reminded: "mdi:bell-ring-outline",
  repeated: "mdi:repeat",
  escalated: "mdi:arrow-up-bold-circle-outline",
  snoozed: "mdi:sleep",
  acknowledged: "mdi:check",
  missed: "mdi:close",
  reopened: "mdi:undo",
  signal_sent: "mdi:send-outline",
  signal_skipped: "mdi:debug-step-over",
};

/** "Quittiert" / "übersprungen" etc. */
export function eventLabel(e: LogEvent, l: Localizer): string {
  return l.t(`ev_${e.kind}` as StringKey);
}

/** Details of an event as one line (stage, person, way, signal, reason). */
export function eventDetail(e: LogEvent, l: Localizer, ruleName?: string): string {
  const parts: string[] = [];
  if (ruleName) parts.push(ruleName);
  if (e.stage) parts.push(l.t("ev_stage", { n: e.stage }));
  if (e.person) parts.push(e.person);
  if (e.via) {
    const key = `via_${e.via}` as StringKey;
    const text = l.t(key);
    parts.push(text === key ? e.via : text);
  }
  if (e.signal_id) parts.push(e.signal_id);
  if (e.detail) {
    if (e.kind === "snoozed") {
      parts.push(e.detail === "until_home" ? l.t("ev_until_home") : e.detail);
    } else {
      const key = `ev_skip_${e.detail}` as StringKey;
      const text = l.t(key);
      parts.push(text === key ? e.detail : text);
    }
  }
  return parts.join(" · ");
}

function row(
  e: LogEvent,
  l: Localizer,
  tz: string | undefined,
  ruleName?: string,
  date = false,
): TemplateResult {
  return html`<div class="ev ${e.kind}">
    <span class="evicon"><ha-icon icon=${KIND_ICONS[e.kind] ?? "mdi:circle-small"}></ha-icon></span>
    <div class="grow">
      <div class="evname">${eventLabel(e, l)}</div>
      <div class="evsub">${eventDetail(e, l, ruleName)}</div>
    </div>
    <span class="evtime">${date ? `${formatDate(e.ts, l, tz)} ` : ""}${formatTime(e.ts, tz)}</span>
  </div>`;
}

/** Flat list (rule editor): date and time per row. */
export function renderEventList(events: LogEvent[], l: Localizer, tz?: string): TemplateResult {
  return html`<div class="evlist">${events.map((e) => row(e, l, tz, undefined, true))}</div>`;
}

/** Newest first, grouped by day with a heading per day. */
export function renderEventTimeline(
  events: LogEvent[],
  l: Localizer,
  tz: string | undefined,
  names: Record<string, string>,
): TemplateResult {
  return html`${groupByDay(events, tz).map(
    (g) =>
      html`<div class="evday">${formatDate(`${g.day}T12:00:00`, l, tz)}</div>
        <div class="evlist">
          ${g.events.map((e) => row(e, l, tz, names[e.rule_id] ?? e.rule_id))}
        </div>`,
  )}`;
}

export const eventStyles = css`
  .evday {
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--lw-text-2);
    margin: 14px 4px 4px;
  }
  .evlist {
    display: flex;
    flex-direction: column;
  }
  .ev {
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 44px;
    padding: 4px 0;
    border-top: 1px solid var(--lw-border);
  }
  .ev:first-child {
    border-top: 0;
  }
  .evicon {
    width: 30px;
    height: 30px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    flex: none;
    background: var(--lw-surface);
    --mdc-icon-size: 18px;
  }
  .ev.acknowledged .evicon {
    background: var(--lw-accent);
    color: var(--lw-on-accent);
  }
  .ev.missed .evicon {
    color: var(--lw-danger);
  }
  .evname {
    font-size: 14px;
    font-weight: 600;
  }
  .evsub,
  .evtime {
    font-size: 12px;
    color: var(--lw-text-2);
  }
  .evtime {
    white-space: nowrap;
  }
  .grow {
    flex: 1;
    min-width: 0;
  }
`;
