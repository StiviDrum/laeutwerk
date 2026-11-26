/** Pure health check of a rule: what would stop it from working as intended. */
import { parseTimespec } from "./builders";
import { entityIdsIn } from "./format";
import type { HomeAssistant, PreviewResult, Rule, UpcomingEvent } from "./types";

export type HealthSeverity = "error" | "warning" | "info";

export interface HealthItem {
  severity: HealthSeverity;
  /** Localization key suffix: `health_<code>`. */
  code:
    | "missing_entity"
    | "unavailable_entity"
    | "no_events"
    | "keyword_unused"
    | "lookahead_short"
    | "no_signals"
    | "push_no_recipient";
  params: Record<string, string>;
}

/** Events of a 90 day preview; `hits` = per keyword whether it occurs at all. */
export interface Preview90 {
  events: Pick<UpcomingEvent, "titles" | "days_until">[];
  hits?: Record<string, boolean>;
}

const RANK: Record<HealthSeverity, number> = { error: 0, warning: 1, info: 2 };

/** Days before the event of the earliest reminder time (0 = none / not before). */
export function earliestOffsetDays(rule: Rule): number {
  let max = 0;
  for (const r of rule.reminders ?? []) {
    const p = parseTimespec(r.at);
    if (!p) continue;
    if (p.kind === "wall" && p.days < 0) max = Math.max(max, -p.days);
    else if (p.kind === "offset" && p.amount < 0) {
      const days = p.unit === "d" ? -p.amount : p.unit === "h" ? -p.amount / 24 : -p.amount / 1440;
      max = Math.max(max, days);
    }
  }
  return max;
}

function keywordHit(row: { match: string; mode?: string }, title: string): boolean {
  const text = title.toLowerCase();
  const key = row.match.trim().toLowerCase();
  if (row.mode === "startswith") return text.startsWith(key);
  if (row.mode === "regex") {
    try {
      return new RegExp(row.match, "i").test(title);
    } catch {
      return true;
    }
  }
  return text.includes(key);
}

/**
 * Health of one rule. `preview90` = events of a preview over 90 days (calendar
 * rules only); without it the event based checks are skipped.
 */
export function healthOf(
  rule: Rule,
  hass: Pick<HomeAssistant, "states"> | undefined,
  preview90?: Preview90,
): HealthItem[] {
  const items: HealthItem[] = [];
  const trigger = !!rule.start_triggers?.length;
  const ids: string[] = [...(trigger ? [] : (rule.sources ?? []))];
  entityIdsIn(
    [
      rule.start_triggers,
      rule.acknowledge,
      rule.activation?.conditions,
      rule.on_done,
      rule.on_missed,
      rule.on_reminded,
      rule.assignee?.substitute_when,
    ],
    ids,
  );
  if (rule.assignee)
    ids.push(
      ...rule.assignee.persons,
      ...(rule.assignee.substitute ? [rule.assignee.substitute] : []),
    );
  for (const s of rule.signals ?? []) {
    ids.push(...(s.entities ?? []), ...(s.players ?? []), ...(s.persons ?? []));
    entityIdsIn([s.when, s.conditions, s.actions], ids);
  }
  if (hass) {
    for (const entity of new Set(ids.filter((id) => id.includes(".")))) {
      const state = hass.states[entity]?.state;
      if (state === undefined)
        items.push({ severity: "error", code: "missing_entity", params: { entity } });
      else if (state === "unavailable")
        items.push({ severity: "warning", code: "unavailable_entity", params: { entity } });
    }
  }
  const lookahead = rule.lookahead_days ?? 14;
  const offset = earliestOffsetDays(rule);
  if (!trigger && !rule.interval && offset > 0 && lookahead <= offset) {
    items.push({
      severity: "error",
      code: "lookahead_short",
      params: { days: String(lookahead), offset: String(Math.ceil(offset)) },
    });
  }
  if (preview90 && !trigger && !rule.interval && rule.sources?.length) {
    if (!preview90.events.some((e) => e.days_until <= lookahead))
      items.push({ severity: "warning", code: "no_events", params: { days: String(lookahead) } });
    for (const row of rule.filter?.keywords?.rows ?? []) {
      if (!row.match.trim()) continue;
      const hit =
        preview90.hits?.[row.match] ??
        preview90.events.some((e) => e.titles.some((t) => keywordHit(row, t)));
      if (!hit)
        items.push({ severity: "info", code: "keyword_unused", params: { keyword: row.match } });
    }
  }
  const signals = rule.signals ?? [];
  if (!signals.some((s) => s.enabled))
    items.push({ severity: "info", code: "no_signals", params: {} });
  signals.forEach((s, i) => {
    if (!s.enabled || s.type !== "notify") return;
    const open = !s.audience || s.audience === "persons";
    if (open && !s.targets?.length && !s.persons?.length)
      items.push({ severity: "error", code: "push_no_recipient", params: { n: String(i + 1) } });
  });
  return items.sort((a, b) => RANK[a.severity] - RANK[b.severity]);
}

/** Worst severity of a list ("" = healthy). */
export function worst(items: HealthItem[]): HealthSeverity | "" {
  return items.reduce<HealthSeverity | "">(
    (w, i) => (w === "" || RANK[i.severity] < RANK[w] ? i.severity : w),
    "",
  );
}

/**
 * 90 day preview of the match part of a rule (`payload` of laeutwerk/preview).
 * The backend returns at most 10 events, so every keyword is asked separately.
 */
export async function fetchPreview90(
  hass: Pick<HomeAssistant, "callWS">,
  payload: Record<string, unknown>,
): Promise<Preview90> {
  const ask = (p: Record<string, unknown>, limit: number) =>
    hass.callWS<PreviewResult>({ type: "laeutwerk/preview", rule: p, limit, days: 90, passes: 1 });
  const all = await ask(payload, 10);
  const filter = payload.filter as { keywords?: { rows?: { match: string }[] } } | undefined;
  const hits: Record<string, boolean> = {};
  await Promise.all(
    (filter?.keywords?.rows ?? []).map(async (row) => {
      const only = {
        ...payload,
        filter: { ...filter, keywords: { ...filter!.keywords, rows: [row] } },
      };
      try {
        hits[row.match] = (await ask(only, 1)).events.length > 0;
      } catch {
        hits[row.match] = true;
      }
    }),
  );
  return { events: all.events, hits };
}

/** Reduced rule for the 90 day preview of a saved rule. */
export function matchPayload(rule: Rule): Record<string, unknown> {
  return {
    sources: rule.sources,
    filter: {
      all_day: rule.filter.all_day,
      keywords: {
        columns: rule.filter.keywords.columns,
        rows: rule.filter.keywords.rows.filter((r) => r.match.trim()),
      },
    },
    bundle: rule.bundle,
    reminders: rule.reminders.length ? rule.reminders : [{ at: "09:00" }],
    expire: rule.expire,
  };
}
