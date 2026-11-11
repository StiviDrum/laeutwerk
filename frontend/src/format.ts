/** Pure display logic of the card (tested with vitest). */
import type { Localizer } from "./localize";
import type { Reminder, Rule, Signal } from "./types";

const DAY_MS = 86_400_000;

export function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function parts(
  date: Date,
  timeZone?: string,
): { y: number; m: number; d: number; wd: number; hm: string } {
  const f = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    year: "numeric",
    month: "numeric",
    day: "numeric",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const get = (type: string) => f.find((p) => p.type === type)?.value ?? "";
  const wd = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].indexOf(get("weekday"));
  return {
    y: Number(get("year")),
    m: Number(get("month")),
    d: Number(get("day")),
    wd,
    hm: `${get("hour")}:${get("minute")}`,
  };
}

/** Whole days between two instants as seen on the local calendar. */
export function dayDiff(a: Date, b: Date, timeZone?: string): number {
  const pa = parts(a, timeZone);
  const pb = parts(b, timeZone);
  return Math.round((Date.UTC(pa.y, pa.m - 1, pa.d) - Date.UTC(pb.y, pb.m - 1, pb.d)) / DAY_MS);
}

export function formatTime(iso: string, timeZone?: string): string {
  return parts(new Date(iso), timeZone).hm;
}

/** "17.11." / "Nov 17". */
export function formatDate(iso: string, l: Localizer, timeZone?: string): string {
  const p = parts(new Date(iso), timeZone);
  if (l.lang.startsWith("de")) return `${p.d}.${p.m}.`;
  return new Intl.DateTimeFormat("en", { timeZone, month: "short", day: "numeric" }).format(
    new Date(iso),
  );
}

/** "heute" / "morgen" / "gestern" / "Do" / "17.11." relative to now. */
export function relativeDay(iso: string, now: Date, l: Localizer, timeZone?: string): string {
  const diff = dayDiff(new Date(iso), now, timeZone);
  if (diff === 0) return l.t("today");
  if (diff === 1) return l.t("tomorrow");
  if (diff === -1) return l.t("yesterday");
  if (Math.abs(diff) < 7) return l.weekdayShort(parts(new Date(iso), timeZone).wd);
  return formatDate(iso, l, timeZone);
}

/** "heute 17:00" / "So 17:00". */
export function relativeDayTime(iso: string, now: Date, l: Localizer, timeZone?: string): string {
  return `${relativeDay(iso, now, l, timeZone)} ${formatTime(iso, timeZone)}`;
}

/** "Morgen: Papier + Bio". */
export function reminderTitle(reminder: {
  titles: string[];
  variables?: Record<string, string>;
}): string {
  const what = reminder.titles.join(" + ");
  const when = reminder.variables?.wann;
  return when ? `${capitalize(when)}: ${what}` : what;
}

/** Status chip of an open reminder: "erinnert 17:00" / "fällig seit gestern". */
export function openStatus(reminder: Reminder, now: Date, l: Localizer, timeZone?: string): string {
  if (!reminder.reminded_at) return "";
  if (dayDiff(new Date(reminder.reminded_at), now, timeZone) === 0) {
    return l.t("reminded_at", { time: formatTime(reminder.reminded_at, timeZone) });
  }
  return l.t("due_since", { when: relativeDay(reminder.reminded_at, now, l, timeZone) });
}

/** "erledigt von Steven · Mo 20:41 · NFC-Tag" / "verpasst · Di 12:00". */
export function finishedLine(
  reminder: Reminder,
  now: Date,
  l: Localizer,
  timeZone?: string,
): string {
  const when = reminder.finished_at ? relativeDayTime(reminder.finished_at, now, l, timeZone) : "";
  if (reminder.state === "missed") return [l.t("missed"), when].filter(Boolean).join(" · ");
  const who = reminder.acknowledged_by
    ? l.t("done_by", { person: reminder.acknowledged_by })
    : l.t("done_plain");
  const via = reminder.acknowledged_via as
    "button" | "service" | "notify_action" | "tag" | "trigger" | null;
  return [who, when, via ? l.t(`via_${via}`) : ""].filter(Boolean).join(" · ");
}

export interface Overview {
  open: { rule: Rule; reminder: Reminder }[];
  upcoming: { rule: Rule; reminder: Reminder }[];
  done: { rule: Rule; reminder: Reminder }[];
}

/** Sort the reminders of all rules into the sections of the overview. */
export function buildOverview(
  rules: Rule[],
  now: Date,
  timeZone?: string,
  only?: string[],
): Overview {
  const result: Overview = { open: [], upcoming: [], done: [] };
  for (const rule of rules) {
    if (only?.length && !only.includes(rule.id ?? "")) continue;
    for (const reminder of rule.status?.reminders ?? []) {
      const item = { rule, reminder };
      if (reminder.state === "reminded") result.open.push(item);
      else if (reminder.state === "planned") result.upcoming.push(item);
      else if (
        reminder.finished_at &&
        dayDiff(new Date(reminder.finished_at), now, timeZone) === 0
      ) {
        result.done.push(item);
      }
    }
  }
  const byStart = (a: { reminder: Reminder }, b: { reminder: Reminder }) =>
    a.reminder.start.localeCompare(b.reminder.start);
  result.open.sort(byStart);
  result.upcoming.sort(byStart);
  result.done.sort((a, b) =>
    (b.reminder.finished_at ?? "").localeCompare(a.reminder.finished_at ?? ""),
  );
  return result;
}

/** Readable form of a reminder time: "Vortag 17:00", "2 h vorher". */
export function describeTimespec(text: string, l: Localizer): string {
  const value = text.trim().toLowerCase().replace(/\s+/g, " ");
  if (value === "event_end") return l.t("at_event_end");
  if (value === "event_start") return l.t("at_event_start");
  const wall = /^(?:(?:([+-]?\d{1,3})d|event_day) )?(\d{1,2}):(\d{2})$/.exec(value);
  if (wall) {
    const days = Number(wall[1] ?? 0);
    const time = `${wall[2].padStart(2, "0")}:${wall[3]}`;
    if (days === 0) return l.t("at_same_day", { time });
    if (days === -1) return l.t("at_day_before", { time });
    return l.t(days < 0 ? "at_days_before" : "at_days_after", { n: Math.abs(days), time });
  }
  const offset = /^(-?)(\d{1,4}) ?([dhm])$/.exec(value);
  if (offset && offset[1] === "-") {
    const n = Number(offset[2]);
    if (offset[3] === "h") return l.t("at_hours_before", { n });
    if (offset[3] === "m") return l.t("at_minutes_before", { n });
    return l.t("at_days_before", { n, time: "" }).trim();
  }
  return text;
}

/** Replace {name} placeholders like the backend does (preview in the editor). */
export function renderTemplate(
  template: string | undefined,
  variables: Record<string, string>,
): string {
  if (!template) return "";
  const text = template.replace(/(?<!\{)\{([^\W\d]\w*)\}(?!\})/gu, (all, name: string) =>
    name in variables ? variables[name] : all,
  );
  return template.startsWith("{") ? capitalize(text) : text;
}

/** All variables a rule offers: fixed ones plus columns and their plurals. */
export function availableVariables(rule: Rule, opportunity = false): string[] {
  const fixed = ["wann", "titel", "rest", "datum", "uhrzeit", "ort", "beschreibung", "kalender"];
  const columns = rule.filter.keywords.columns.flatMap((c) => [c, `${c}n`]);
  return [...columns, ...fixed, ...(opportunity ? ["person"] : [])];
}

/** "blinkt bei Gelegenheit · max. 1× · nicht 0–10 Uhr". */
export function signalSummary(signal: Signal, l: Localizer): string {
  const bits: string[] = [];
  bits.push(signal.when === "now" ? l.t("s_now") : l.t("s_opportunity"));
  if (signal.type === "notify") {
    const who =
      signal.audience === "all"
        ? l.t("audience_all")
        : signal.audience === "present"
          ? l.t("audience_present")
          : signal.audience === "persons"
            ? (signal.persons ?? []).map((p) => p.replace("person.", "")).join(", ")
            : (signal.targets ?? [])
                .map((t) => t.replace(/^notify\.(mobile_app_)?/, ""))
                .join(", ");
    if (who) bits.push(l.t("s_to", { who }));
  }
  if (signal.type === "light_signal") {
    bits.push(
      `${l.t(signal.pattern?.effect === "pulse" ? "effect_pulse" : "effect_blink")} ${signal.pattern?.count ?? 3}×`,
    );
  }
  if (signal.limit?.per_reminder) bits.push(l.t("s_max", { n: signal.limit.per_reminder }));
  for (const quiet of signal.quiet ?? []) {
    bits.push(l.t("s_quiet", { from: shortClock(quiet.from), to: shortClock(quiet.to) }));
  }
  if (signal.conditions?.length) bits.push(l.t("s_only_if"));
  return bits.join(" · ");
}

function shortClock(value: string): string {
  const [h, m] = value.split(":");
  return m === "00" ? String(Number(h)) : `${Number(h)}:${m}`;
}

export const SIGNAL_ICONS: Record<string, string> = {
  notify: "mdi:cellphone-message",
  light_signal: "mdi:lightbulb-on-outline",
  announce: "mdi:bullhorn-outline",
  action: "mdi:cog-play-outline",
};

/** A new signal with sensible defaults for its type. */
export function defaultSignal(type: Signal["type"], rule: Rule): Signal {
  const first = rule.filter.keywords.columns[0];
  const what = first ? `{${first}n}` : "{titel}";
  const base = { type, enabled: true, when: "now" as const };
  if (type === "notify") {
    return {
      ...base,
      audience: "present",
      title: `{wann}: ${what}`,
      message: rule.name,
      actions: [{ ack: true, label: rule.ack_label || "OK" }],
    };
  }
  if (type === "light_signal") {
    const colorColumn = ["farbe", "color", "colour"].find((c) =>
      rule.filter.keywords.columns.includes(c),
    );
    return {
      ...base,
      entities: [],
      pattern: { effect: "blink", count: 3 },
      ...(colorColumn ? { color_from: colorColumn } : {}),
      restore: true,
      limit: { per_reminder: 1 },
    };
  }
  if (type === "announce") {
    return { ...base, players: [], text: `{wann}: ${what}`, limit: { per_reminder: 1 } };
  }
  return { ...base, actions: [] };
}

/** An empty rule for the "new rule" editor. */
export function emptyRule(): Rule {
  return {
    name: "",
    icon: null,
    color: null,
    enabled: true,
    sources: [],
    filter: { all_day: false, keywords: { columns: [], rows: [] } },
    reminders: [{ at: "-1d 17:00" }],
    signals: [],
    acknowledge: [],
    ack_label: null,
    repeat: "none",
    bundle: true,
    expire: "event_end",
  };
}

/** Rename a keyword column in the table and wherever signals refer to it. */
export function renameColumn(rule: Rule, index: number, name: string): Rule {
  const old = rule.filter.keywords.columns[index];
  const clean = name
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}_]/gu, "_");
  const columns = rule.filter.keywords.columns.map((c, i) => (i === index ? clean : c));
  const rows = rule.filter.keywords.rows.map((row) => {
    const next: typeof row = { match: row.match };
    if (row.mode) next.mode = row.mode;
    rule.filter.keywords.columns.forEach((c, i) => {
      next[columns[i]] = row[c] ?? "";
    });
    return next;
  });
  const signals = rule.signals.map((s) => (s.color_from === old ? { ...s, color_from: clean } : s));
  return { ...rule, signals, filter: { ...rule.filter, keywords: { columns, rows } } };
}
