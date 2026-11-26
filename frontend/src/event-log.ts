/** Pure helpers of the history: filters, per-rule statistics, grouping by day. */
import type { LogEvent, LogKind } from "./types";

export const LOG_KINDS: LogKind[] = [
  "reminded",
  "repeated",
  "escalated",
  "acknowledged",
  "missed",
  "snoozed",
  "signal_sent",
  "signal_skipped",
];

export interface RuleStats {
  acknowledged: number;
  missed: number;
  /** Average minutes between the first reminder and the acknowledgement (undefined: none). */
  avgOpenMinutes?: number;
}

export function ruleStats(events: LogEvent[]): Record<string, RuleStats> {
  const out: Record<string, RuleStats & { sum: number; n: number }> = {};
  const reminded = new Map<string, number>();
  const sorted = [...events].sort((a, b) => a.ts.localeCompare(b.ts));
  for (const e of sorted) {
    const s = (out[e.rule_id] ??= { acknowledged: 0, missed: 0, sum: 0, n: 0 });
    const key = `${e.rule_id}/${e.reminder_id}`;
    if (e.kind === "reminded" && !reminded.has(key)) reminded.set(key, Date.parse(e.ts));
    else if (e.kind === "missed") s.missed++;
    else if (e.kind === "acknowledged") {
      s.acknowledged++;
      const start = reminded.get(key);
      if (start !== undefined) {
        s.sum += Math.max(0, Date.parse(e.ts) - start) / 60000;
        s.n++;
      }
    }
  }
  const result: Record<string, RuleStats> = {};
  for (const [id, s] of Object.entries(out)) {
    result[id] = {
      acknowledged: s.acknowledged,
      missed: s.missed,
      avgOpenMinutes: s.n ? s.sum / s.n : undefined,
    };
  }
  return result;
}

/** Events newest first, grouped by local day (key "YYYY-MM-DD"). */
export function groupByDay(
  events: LogEvent[],
  timeZone?: string,
): { day: string; events: LogEvent[] }[] {
  const fmt = new Intl.DateTimeFormat("en-CA", { timeZone });
  const groups: { day: string; events: LogEvent[] }[] = [];
  for (const e of [...events].sort((a, b) => b.ts.localeCompare(a.ts))) {
    const day = fmt.format(new Date(e.ts));
    const last = groups[groups.length - 1];
    if (last?.day === day) last.events.push(e);
    else groups.push({ day, events: [e] });
  }
  return groups;
}

/** "5 min", "2 h 10 min", "1,5 d" style short duration. */
export function shortDuration(minutes: number): string {
  const m = Math.round(minutes);
  if (m < 60) return `${m} min`;
  if (m < 48 * 60) return `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ""}`;
  return `${Math.round(m / 1440)} d`;
}

/** Counts of acknowledged / missed events since the given instant. */
export function countSince(
  events: LogEvent[],
  sinceMs: number,
): { acknowledged: number; missed: number } {
  let acknowledged = 0;
  let missed = 0;
  for (const e of events) {
    if (Date.parse(e.ts) < sinceMs) continue;
    if (e.kind === "acknowledged") acknowledged++;
    else if (e.kind === "missed") missed++;
  }
  return { acknowledged, missed };
}
