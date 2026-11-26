/** Pure grouping of the "Week" tab: planned passes of all active rules per day. */
import type { PreviewPass, Rule, UpcomingEvent } from "./types";

export interface WeekItem {
  at: string;
  ruleId: string;
  ruleName: string;
  title: string;
  /** Planned by a snooze (reminder is open and was postponed). */
  snoozed: boolean;
  /** Passes after the first one of the same event. */
  followUp: boolean;
}

export interface WeekDay {
  /** Local date "YYYY-MM-DD". */
  day: string;
  items: WeekItem[];
}

export function localDay(iso: string | Date, timeZone?: string): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone }).format(new Date(iso));
}

/** Passes of one rule as items; `events` give the title of each pass. */
export function itemsOf(rule: Rule, passes: PreviewPass[], events: UpcomingEvent[]): WeekItem[] {
  const byId = new Map(events.map((e) => [e.id, e]));
  const snoozed = new Set(
    (rule.status?.reminders ?? []).filter((r) => r.snoozed_until).map((r) => r.snoozed_until),
  );
  return passes.map((p) => {
    const e = byId.get(p.event_id);
    return {
      at: p.at,
      ruleId: rule.id ?? "",
      ruleName: rule.name,
      title: e?.headline || e?.titles.join(" + ") || rule.name,
      snoozed: snoozed.has(p.at),
      followUp: p.kind !== "first",
    };
  });
}

/**
 * Seven day buckets starting today. Items before now that are still planned
 * (due today) stay in today's bucket, sorted by time.
 */
export function groupWeek(items: WeekItem[], today: Date, timeZone?: string): WeekDay[] {
  const start = new Date(localDay(today, timeZone) + "T12:00:00Z");
  const days: WeekDay[] = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(start.getTime() + i * 86400_000);
    days.push({ day: d.toISOString().slice(0, 10), items: [] });
  }
  for (const item of items) {
    const day = localDay(item.at, timeZone);
    const bucket = days.find((d) => d.day === day) ?? (day < days[0].day ? days[0] : undefined);
    bucket?.items.push(item);
  }
  for (const d of days) d.items.sort((a, b) => a.at.localeCompare(b.at));
  return days;
}

/** Rules that start by a trigger (no fixed time), enabled ones only. */
export const triggerRules = (rules: Rule[]): Rule[] =>
  rules.filter((r) => r.enabled && !!r.start_triggers?.length && r.id);

/** Rules that are planned by time. */
export const timedRules = (rules: Rule[]): Rule[] =>
  rules.filter((r) => r.enabled && !r.start_triggers?.length && r.id);
