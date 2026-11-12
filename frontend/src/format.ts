/** Pure display logic of the card (tested with vitest). */
import type { Localizer, StringKey } from "./localize";
import type { Badge, ColumnSpec, EarlySetting, Reminder, Rule, Signal } from "./types";

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

/** "Morgen: Papier + Bio" (or the rule's own headline when the backend sent one). */
export function reminderTitle(reminder: {
  titles: string[];
  variables?: Record<string, string>;
  headline?: string | null;
}): string {
  const own = reminder.headline?.trim();
  if (own) return own;
  const what = (reminder.titles ?? []).join(" + ");
  const when = reminder.variables?.wann;
  return when ? `${capitalize(when)}: ${what}` : what;
}

/** Default icon of rules without an own one. */
export const DEFAULT_ICON = "mdi:bell-ring-outline";

/**
 * Icon and colour of one keyword badge. Both fall back independently:
 * keyword -> rule -> default (colour: null = caller's default).
 */
export function badgeLook(
  rule: { icon?: string | null; color?: string | null } | undefined,
  badge: Partial<Badge> | undefined,
  defaultIcon = DEFAULT_ICON,
): Badge & { icon: string } {
  return {
    icon: badge?.icon || rule?.icon || defaultIcon,
    color: badge?.color || rule?.color || null,
  };
}

/**
 * Distinct looks of a reminder/event, in order (at least one); without
 * badges just the rule's look.
 */
export function badgeLooks(
  rule: { icon?: string | null; color?: string | null } | undefined,
  item: { badges?: Badge[] } | undefined,
  defaultIcon = DEFAULT_ICON,
): (Badge & { icon: string })[] {
  const source: Partial<Badge>[] = item?.badges ?? [];
  const looks: (Badge & { icon: string })[] = [];
  for (const badge of source) {
    const look = badgeLook(rule, badge, defaultIcon);
    if (!looks.some((x) => x.icon === look.icon && x.color === look.color)) looks.push(look);
  }
  return looks.length ? looks : [badgeLook(rule, undefined, defaultIcon)];
}

/** Headline preview in the editor: own template (plural for bundles) or the default. */
export function headlinePreview(
  rule: { headline?: string | null; headline_plural?: string | null },
  event: { titles: string[]; variables?: Record<string, string> } | undefined,
): string {
  if (!event) return "";
  const plural = event.titles.length > 1 ? rule.headline_plural?.trim() : "";
  const template = plural || rule.headline?.trim();
  return template
    ? renderTemplate(template, event.variables ?? {})
    : reminderTitle({ titles: event.titles, variables: event.variables });
}

/** Variable suggestions for a text field: `{na` at the cursor offers names starting with "na". */
export function variableQuery(
  text: string,
  cursor: number,
): { start: number; query: string } | null {
  const m = /\{([^\W\d]\w*)?$/u.exec(text.slice(0, cursor));
  return m ? { start: m.index, query: m[1] ?? "" } : null;
}

/** Insert `{name}` in place of the typed `{query` (and a directly following `}`). */
export function insertVariable(
  text: string,
  cursor: number,
  name: string,
): { text: string; cursor: number } | null {
  const q = variableQuery(text, cursor);
  if (!q) return null;
  const tail = text.slice(cursor);
  const after = tail.replace(/^\w*\}?/u, "");
  const insert = `{${name}}`;
  return { text: text.slice(0, q.start) + insert + after, cursor: q.start + insert.length };
}

/** Case-insensitive filtering of suggestions (prefix matches first). */
export function filterSuggestions<T extends { value: string; label?: string }>(
  items: T[],
  query: string,
  limit = 8,
): T[] {
  const q = query.trim().toLowerCase();
  if (!q) return items.slice(0, limit);
  const hay = (i: T) => `${i.value} ${i.label ?? ""}`.toLowerCase();
  const starts = items.filter((i) => i.value.toLowerCase().startsWith(q));
  const rest = items.filter((i) => !starts.includes(i) && hay(i).includes(q));
  return [...starts, ...rest].slice(0, limit);
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
    if (rule.visible === false || (only?.length && !only.includes(rule.id ?? ""))) continue;
    for (const reminder of rule.status?.reminders ?? []) {
      const item = { rule, reminder };
      if (reminder.state === "reminded") result.open.push(item);
      else if (reminder.state === "planned") result.upcoming.push(item);
      else if (
        (reminder.finished_at && dayDiff(new Date(reminder.finished_at), now, timeZone) === 0) ||
        canReopen(reminder, now)
      ) {
        // Finished today, or done ahead and still undoable (event not over).
        result.done.push(item);
      }
    }
  }
  const byStart = (a: { reminder: Reminder }, b: { reminder: Reminder }) =>
    a.reminder.start.localeCompare(b.reminder.start);
  result.open.sort(byStart);
  result.upcoming.sort(byStart);
  // Today's first (newest on top), then the ones done ahead by event date.
  const today = (r: Reminder) =>
    !!r.finished_at && dayDiff(new Date(r.finished_at), now, timeZone) === 0;
  result.done.sort((a, b) => {
    const ta = today(a.reminder) && !isAhead(a.reminder, now);
    const tb = today(b.reminder) && !isAhead(b.reminder, now);
    if (ta !== tb) return ta ? -1 : 1;
    if (ta) return (b.reminder.finished_at ?? "").localeCompare(a.reminder.finished_at ?? "");
    return a.reminder.start.localeCompare(b.reminder.start);
  });
  return result;
}

/** Whether an acknowledged reminder can still be reopened (not expired yet). */
export function canReopen(reminder: Reminder, now: Date): boolean {
  return (
    reminder.state === "done" &&
    !!reminder.expires_at &&
    new Date(reminder.expires_at).getTime() > now.getTime()
  );
}

/** Done before its event started (acknowledged ahead of time). */
export function isAhead(reminder: Reminder, now: Date): boolean {
  return reminder.state === "done" && new Date(reminder.start).getTime() > now.getTime();
}

/** Done tasks that can still be undone, by event date (compact dialog). */
export function doneTasks(rules: Rule[], now: Date, only?: string[]): Task[] {
  const list: Task[] = [];
  for (const rule of rules) {
    if (rule.visible === false || (only?.length && !only.includes(rule.id ?? ""))) continue;
    for (const reminder of rule.status?.reminders ?? []) {
      if (canReopen(reminder, now)) list.push({ rule, reminder, open: false });
    }
  }
  return list.sort((a, b) => a.reminder.start.localeCompare(b.reminder.start));
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
  capitalizeFirst = true,
): string {
  if (!template) return "";
  const text = template.replace(/(?<!\{)\{([^\W\d]\w*)\}(?!\})/gu, (all, name: string) =>
    name in variables ? variables[name] : all,
  );
  return capitalizeFirst && template.startsWith("{") ? capitalize(text) : text;
}

/** Sample values for the time variables (preview only; `nr` 2 for repeat texts). */
export function timeSamples(l: Localizer, nr = 1): Record<string, string> {
  return { seit: l.t("sample_since"), seit_min: "25", erinnert_um: "19:42", nr: String(nr) };
}

/** Preview of a repeat text: the repeat variant (nr = 2) if set, else the normal text. */
export function repeatPreview(
  repeat: string | undefined,
  normal: string | undefined,
  sample: Record<string, string>,
  l: Localizer,
): string {
  return renderTemplate(repeat?.trim() ? repeat : normal, { ...sample, ...timeSamples(l, 2) });
}

/** Stage of a signal: a number, or "every" (every_stage, stage cleared); they exclude each other. */
export function withSignalStage(signal: Signal, stage: number | "every"): Signal {
  const rest = { ...signal };
  delete rest.stage;
  delete rest.every_stage;
  if (stage === "every") return { ...rest, every_stage: true };
  return stage ? { ...rest, stage } : rest;
}

/** Stage with a new `min_age` (empty = removed). */
export function withMinAge<T extends { min_age?: string }>(stage: T, minAge: string): T {
  const next = { ...stage };
  if (minAge.trim()) next.min_age = minAge.trim();
  else delete next.min_age;
  return next;
}

/** Names of the {variables} used in a text. */
export function templateVariables(template: string | undefined): string[] {
  return [...(template ?? "").matchAll(/(?<!\{)\{([^\W\d]\w*)\}(?!\})/gu)].map((m) => m[1]);
}

/** Variables a tag id may use: keyword columns (and plurals) plus the event ones. */
export function tagVariables(rule: Rule): string[] {
  return availableVariables(rule).filter(
    (name) =>
      !["wann", "datum", "uhrzeit", "seit", "seit_min", "erinnert_um", "nr", "zustaendig"].includes(
        name,
      ),
  );
}

/** Tag acknowledgements whose variables all exist (safe to send to the preview). */
export function validTagAcks(rule: Rule): { type: "tag"; tag_id: string }[] {
  const known = new Set([...availableVariables(rule), "wann", "datum", "uhrzeit"]);
  return rule.acknowledge
    .filter((a) => a.type === "tag" && a.tag_id?.trim())
    .filter((a) => templateVariables(a.tag_id).every((name) => known.has(name)))
    .map((a) => ({ type: "tag" as const, tag_id: a.tag_id!.trim() }));
}

/** Name of a keyword column. */
export function colName(spec: ColumnSpec): string {
  return typeof spec === "string" ? spec : spec.name;
}

/** Plural variable of a column ("<name>n" by default), null if switched off. */
export function colPlural(spec: ColumnSpec): string | null {
  const name = colName(spec);
  const plural = typeof spec === "string" ? true : (spec.plural ?? true);
  if (plural === false) return null;
  if (plural === true || !plural) return `${name}n`;
  return plural;
}

/** Short form (the name) while the plural is the default, like the backend stores it. */
export function makeColumn(name: string, plural: string | null): ColumnSpec {
  if (plural === `${name}n`) return name;
  return { name, plural: plural ?? false };
}

export function columnNames(rule: Rule): string[] {
  return rule.filter.keywords.columns.map(colName);
}

/** Switch the plural variable of a column on (default name) or off. */
export function setColumnPlural(rule: Rule, index: number, on: boolean): Rule {
  const columns = rule.filter.keywords.columns.map((c, i) =>
    i === index ? makeColumn(colName(c), on ? `${colName(c)}n` : null) : c,
  );
  return { ...rule, filter: { ...rule.filter, keywords: { ...rule.filter.keywords, columns } } };
}

/** All variables a rule offers: fixed ones plus columns and their plurals. */
export function availableVariables(rule: Rule, opportunity = false): string[] {
  const fixed = [
    "wann",
    "titel",
    "rest",
    "datum",
    "uhrzeit",
    "seit",
    "seit_min",
    "erinnert_um",
    "nr",
    "ort",
    "beschreibung",
    "kalender",
  ];
  const columns = rule.filter.keywords.columns.flatMap((c) => {
    const plural = colPlural(c);
    return plural ? [colName(c), plural] : [colName(c)];
  });
  return [
    ...columns,
    ...fixed,
    ...(rule.assignee?.persons.length ? ["zustaendig"] : []),
    ...(opportunity ? ["person"] : []),
  ];
}

/** "blinkt bei Gelegenheit · max. 1× · nicht 0–10 Uhr". */
/** Default stage colours (stage 1, 2, …) when a stage has none of its own. */
export const STAGE_COLORS = ["#ffb020", "#ff5a6e", "#c58cff", "#6fa8ff", "#4ad295"];

/** Colour of an escalation stage; null for stage 0 (from the start). */
export function stageColor(rule: Rule, stage: number | undefined): string | null {
  if (!stage) return null;
  return rule.escalation?.[stage - 1]?.color ?? STAGE_COLORS[(stage - 1) % STAGE_COLORS.length];
}

function entityIdsIn(node: unknown, found: string[]): void {
  if (Array.isArray(node)) {
    node.forEach((item) => entityIdsIn(item, found));
  } else if (node && typeof node === "object") {
    for (const [key, value] of Object.entries(node)) {
      if (key === "entity_id") {
        for (const id of Array.isArray(value) ? value : [value]) {
          if (typeof id === "string" && id.includes(".") && !id.includes("{")) found.push(id);
        }
      } else {
        entityIdsIn(value, found);
      }
    }
  }
}

/** Who / what a signal reaches, by name (lamps, speakers, persons, entities). */
export function signalTargets(
  signal: Signal,
  l: Localizer,
  names: (entityId: string) => string = (id) => id,
): string[] {
  if (signal.type === "light_signal") return (signal.entities ?? []).map(names);
  if (signal.type === "announce") return (signal.players ?? []).map(names);
  if (signal.type === "action") {
    const found: string[] = [];
    entityIdsIn(signal.actions, found);
    return [...new Set(found)].map(names);
  }
  const who: string[] = [];
  if (signal.audience === "assignee") who.push(l.t("audience_assignee"));
  else if (signal.audience === "all") who.push(l.t("audience_all"));
  else if (signal.audience === "present") who.push(l.t("audience_present"));
  else if (signal.audience === "persons") {
    const persons = (signal.persons ?? []).map(names).join(", ");
    who.push(signal.only_present ? `${persons} (${l.t("audience_present")})` : persons);
  }
  for (const target of signal.targets ?? []) who.push(target.replace(/^notify\./, ""));
  return who.filter(Boolean);
}

/** "Licht · Stehleuchte", "Push · Steven, Anna". */
export function signalTitle(
  signal: Signal,
  l: Localizer,
  names?: (entityId: string) => string,
): string {
  const type = l.t(`type_${signal.type}` as StringKey);
  const targets = signalTargets(signal, l, names);
  return targets.length ? `${type} · ${targets.join(", ")}` : type;
}

/** Short description below the title: when, pattern, limits, quiet times. */
export function signalSummary(signal: Signal, l: Localizer): string {
  const bits: string[] = [];
  bits.push(signal.when === "now" ? l.t("s_now") : l.t("s_opportunity"));
  if (signal.type === "light_signal") {
    bits.push(
      `${l.t(signal.pattern?.effect === "pulse" ? "effect_pulse" : "effect_blink")} ${signal.pattern?.count ?? 3}×`,
    );
  }
  if (signal.every_stage) bits.push(l.t("every_reminder"));
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
export function defaultSignal(type: Signal["type"], rule: Rule, done = "OK"): Signal {
  const first = rule.filter.keywords.columns[0];
  const what = first ? `{${colPlural(first) ?? colName(first)}}` : "{titel}";
  const base = { type, enabled: true, when: "now" as const };
  if (type === "notify") {
    return {
      ...base,
      audience: "present",
      title: `{wann}: ${what}`,
      message: rule.name,
      actions: [{ ack: true, label: done }],
    };
  }
  if (type === "light_signal") {
    const colorColumn = ["farbe", "color", "colour"].find((c) => columnNames(rule).includes(c));
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
    visible: true,
    lookahead_days: 14,
    sources: [],
    filter: { all_day: false, keywords: { columns: [], rows: [] } },
    reminders: [{ at: "-1d 17:00" }],
    signals: [],
    acknowledge: [],
    ack_label: null,
    repeat: "none",
    bundle: true,
    expire: "event_end",
    interval: null,
    activation: null,
    early: { mode: "hours", hours: 24 },
    on_done: [],
    assignee: null,
    escalation: [],
  };
}

/** A new rule from a template: template values over the empty rule. */
export function ruleFromTemplate(template: { rule: Partial<Rule> }): Rule {
  const base = emptyRule();
  const rule = JSON.parse(JSON.stringify(template.rule)) as Partial<Rule>;
  return {
    ...base,
    ...rule,
    filter: {
      all_day: rule.filter?.all_day ?? false,
      keywords: {
        columns: rule.filter?.keywords?.columns ?? [],
        rows: rule.filter?.keywords?.rows ?? [],
      },
    },
    sources: rule.sources ?? [],
    enabled: true,
  };
}

/** Whether a rule can be saved (name, a time, and a source or an interval). */
export function ruleComplete(rule: Rule): boolean {
  if (rule.start_triggers) return !!(rule.name.trim() && rule.start_triggers.length);
  return !!(rule.name.trim() && rule.reminders.length && (rule.sources.length || rule.interval));
}

export type SourceMode = "calendar" | "trigger" | "interval";

/** Source mode of a stored rule (exactly one source is ever kept). */
export function sourceModeOf(rule: Rule): SourceMode {
  if (rule.start_triggers?.length) return "trigger";
  if (rule.interval && !rule.sources.length) return "interval";
  return "calendar";
}

/** The rule reduced to the source of the chosen mode; the other two are cleared. */
export function keepOnlySource(rule: Rule, mode: SourceMode): Rule {
  const next: Rule = { ...rule };
  if (mode !== "calendar") {
    next.sources = [];
    next.filter = { all_day: false, keywords: { columns: [], rows: [] } };
  }
  if (mode === "trigger") {
    next.start_triggers = rule.start_triggers ?? [];
    next.interval = null;
    if (!/^\+\d+h$/.test(next.expire.trim())) next.expire = "+12h";
  } else {
    delete next.start_triggers;
    if (mode === "interval") next.interval = rule.interval ?? { every: 90 };
    else next.interval = null;
    if (/^\+\d+h$/.test(next.expire.trim())) next.expire = "event_day 12:00";
  }
  return next;
}

/** "Alida (Vertretung für Steven)" or just the name. */
export function assigneeText(l: Localizer, name: string, substituteFor?: string | null): string {
  return substituteFor ? l.t("substitute_for", { name, for: substituteFor }) : name;
}

/** Rename a keyword column in the table and wherever signals refer to it. */
export function renameColumn(rule: Rule, index: number, name: string): Rule {
  const spec = rule.filter.keywords.columns[index];
  const old = colName(spec);
  const clean = name
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}_]/gu, "_");
  // Keep the plural setting: default name follows, off stays off, own name stays.
  const plural = colPlural(spec);
  const nextPlural = plural === `${old}n` ? `${clean}n` : plural;
  const columns = rule.filter.keywords.columns.map((c, i) =>
    i === index ? makeColumn(clean, nextPlural) : c,
  );
  const names = columns.map(colName);
  const rows = rule.filter.keywords.rows.map((row) => {
    const next: typeof row = { match: row.match };
    if (row.mode) next.mode = row.mode;
    rule.filter.keywords.columns.forEach((c, i) => {
      next[names[i]] = row[colName(c)] ?? "";
    });
    return next;
  });
  const signals = rule.signals.map((s) => (s.color_from === old ? { ...s, color_from: clean } : s));
  return { ...rule, signals, filter: { ...rule.filter, keywords: { columns, rows } } };
}

// --- 0.7: step summaries, checks before saving, readable server errors ------

/** Short summary of an editor step for its collapsed header. */
export function stepSummary(
  rule: Rule,
  step: number,
  l: Localizer,
  names: (entityId: string) => string = (id) => id,
): string {
  switch (step) {
    case 1: {
      const parts = rule.sources.map(names);
      if (rule.interval) parts.push(l.t("sum_interval", { n: String(rule.interval.every) }));
      return parts.join(", ") || "–";
    }
    case 2: {
      const rows = rule.filter.keywords.rows.filter((r) => r.match.trim());
      const parts = [rows.length ? l.t("sum_keywords", { n: rows.length }) : l.t("sum_all_events")];
      if (rule.filter.all_day) parts.push(l.t("sum_all_day"));
      return parts.join(" · ");
    }
    case 3: {
      if (rule.start_triggers) {
        const rp = rule.repeat;
        if (rp === "none") return l.t("repeat_once");
        return (
          l.t("sum_repeat_every", { n: String(rp.every) }) + (rp.max ? `, max. ${rp.max}×` : "")
        );
      }
      const parts = rule.reminders.map((r) => describeTimespec(r.at, l));
      if (rule.repeat !== "none") parts.push(l.t("sum_repeat"));
      return parts.join(" · ") || "–";
    }
    case 4: {
      const active = rule.signals.filter((s) => s.enabled);
      if (!active.length) return l.t("sum_no_signals");
      const types = [...new Set(active.map((s) => l.t(`type_${s.type}` as StringKey)))];
      return types.join(", ");
    }
    case 5: {
      const ways: string[] = [];
      const pushDone = rule.signals.some(
        (s) => s.type === "notify" && (s.actions ?? []).some((a) => (a as { ack?: boolean }).ack),
      );
      if (pushDone) ways.push(l.t("sum_push_button"));
      const tags = rule.acknowledge.filter((a) => a.type === "tag").length;
      if (tags) ways.push(l.t("sum_tags", { n: tags }));
      const triggers = rule.acknowledge.filter((a) => a.type === "trigger").length;
      if (triggers) ways.push(l.t("sum_triggers", { n: triggers }));
      return ways.join(", ") || l.t("sum_card_only");
    }
    case 6: {
      const expire = rule.expire.trim();
      const day = /^event_day (\d{1,2}:\d{2})$/.exec(expire);
      const exp =
        expire === "event_end"
          ? l.t("expire_event_end")
          : day
            ? `${l.t("expire_event_day")} ${day[1]}`
            : expire;
      return [
        rule.bundle && !rule.start_triggers ? l.t("sum_bundled") : "",
        `${l.t("expire")}: ${exp}`,
      ]
        .filter(Boolean)
        .join(" · ");
    }
    default: {
      const parts: string[] = [];
      if (rule.assignee?.persons.length) parts.push(l.t("assignee"));
      if (rule.activation) parts.push(l.t("activation"));
      if (rule.escalation?.length) {
        parts.push(l.t("sum_stages", { n: rule.escalation.length }));
      }
      if (rule.on_done?.length) parts.push(l.t("on_done"));
      return parts.join(" · ") || "–";
    }
  }
}

export interface Problem {
  step: number;
  text: string;
}

/** What is still missing before a rule can be saved (checked in the card). */
export function ruleProblems(rule: Rule, l: Localizer): Problem[] {
  const problems: Problem[] = [];
  if (!rule.name.trim()) problems.push({ step: 1, text: l.t("err_name") });
  if (rule.start_triggers) {
    if (!rule.start_triggers.length) problems.push({ step: 1, text: l.t("err_trigger") });
  } else if (!rule.sources.length && !rule.interval) {
    problems.push({ step: 1, text: l.t("err_source") });
  }
  if (rule.filter.keywords.rows.some((r) => !r.match.trim())) {
    problems.push({ step: 2, text: l.t("err_keyword_empty") });
  }
  const names = columnNames(rule);
  if (names.some((n) => !n) || new Set(names).size !== names.length) {
    problems.push({ step: 2, text: l.t("err_columns") });
  }
  if (!rule.reminders.length && !rule.start_triggers) {
    problems.push({ step: 3, text: l.t("err_time") });
  }
  rule.signals.forEach((s) => {
    const label = l.t(`type_${s.type}` as StringKey);
    if (s.type === "notify" && !s.targets?.length && !s.audience) {
      problems.push({ step: 4, text: l.t("err_push_recipients", { signal: label }) });
    }
    if (s.type === "notify" && s.audience === "persons" && !s.persons?.length) {
      problems.push({ step: 4, text: l.t("err_push_recipients", { signal: label }) });
    }
    if (s.type === "light_signal" && !s.entities?.length) {
      problems.push({ step: 4, text: l.t("err_light", { signal: label }) });
    }
    if (s.type === "announce" && (!s.players?.length || !s.text?.trim())) {
      problems.push({ step: 4, text: l.t("err_announce", { signal: label }) });
    }
    if (s.type === "notify" && !s.message?.trim()) {
      problems.push({ step: 4, text: l.t("err_message", { signal: label }) });
    }
  });
  if (rule.acknowledge.some((a) => a.type === "tag" && !a.tag_id?.trim())) {
    problems.push({ step: 5, text: l.t("err_tag_empty") });
  }
  const season = rule.activation?.season;
  if (season && (!season.from || !season.to)) {
    problems.push({ step: 7, text: l.t("err_season") });
  }
  const who = rule.assignee;
  if (who && !!who.substitute !== !!who.substitute_when?.entity_id) {
    problems.push({ step: 7, text: l.t("err_substitute") });
  }
  if ((rule.escalation ?? []).some((e) => !e.after.trim())) {
    problems.push({ step: 7, text: l.t("err_stage") });
  }
  return problems;
}

/** Which editor step a server validation message belongs to. */
export function errorStep(message: string): number | undefined {
  const path = /at '([^']+)'/.exec(message)?.[1] ?? "";
  const key = path.split(/[.[]/)[0];
  const byKey: Record<string, number> = {
    name: 1,
    icon: 1,
    color: 1,
    sources: 1,
    interval: 1,
    filter: 2,
    reminders: 3,
    repeat: 3,
    signals: 4,
    acknowledge: 5,
    ack_label: 5,
    bundle: 6,
    expire: 6,
    activation: 7,
    assignee: 7,
    escalation: 7,
    on_done: 7,
  };
  if (key in byKey) return byKey[key];
  if (/^signal '/.test(message)) return 4;
  if (/^acknowledge \d/.test(message)) return 5;
  if (/^(activation|on_done):/.test(message)) return 7;
  if (/column|keyword row/.test(message)) return 2;
  if (/source or an 'interval'|cannot be a source/.test(message)) return 1;
  if (/reminder times|invalid time/.test(message)) return 3;
  if (/stage|escalation/.test(message)) return 7;
  return undefined;
}

/** Common server messages in plain words (the original stays as detail). */
export function translateError(message: string, l: Localizer): string {
  const known: [RegExp, StringKey][] = [
    [/must not be empty/, "srv_empty"],
    [/length of value must be at least 1/, "srv_empty_list"],
    [/required key not provided/, "srv_required"],
    [/not a valid value|expected .* for dictionary value/, "srv_invalid"],
    [/cannot be a source/, "srv_source"],
    [/at least one source or an 'interval'/, "err_source"],
    [/invalid time/, "srv_time"],
    [/is not a .* entity/, "srv_entity"],
    [/unknown variable/, "srv_variable"],
    [/clashes with another variable/, "srv_plural_clash"],
    [/already exists/, "srv_exists"],
    [/stage \d+ does not exist/, "srv_stage"],
    [/Entity .* is neither a valid entity ID|not a valid entity id/i, "srv_entity"],
  ];
  const hit = known.find(([pattern]) => pattern.test(message));
  return hit ? l.t(hit[1]) : message;
}

// --- 0.7.1: next task (compact card) and the done label ---------------------

/** Label of "done" for a rule: its push button text, else "Erledigt". */
export function doneLabel(rule: Rule, l: Localizer): string {
  for (const signal of rule.signals) {
    if (signal.type !== "notify") continue;
    const button = (signal.actions ?? []).find((a) => (a as { ack?: boolean }).ack) as
      { label?: string } | undefined;
    if (button?.label) return button.label;
  }
  return rule.ack_label || l.t("done");
}

export interface Task {
  rule: Rule;
  reminder: Reminder;
  /** Reminding now (else planned). */
  open: boolean;
}

/**
 * All tasks of some rules: reminding ones first (the one that expires first
 * on top), then planned ones by their next reminder time.
 */
export function tasks(rules: Rule[], only?: string[]): Task[] {
  const list: Task[] = [];
  for (const rule of rules) {
    if (rule.visible === false || (only?.length && !only.includes(rule.id ?? ""))) continue;
    for (const reminder of rule.status?.reminders ?? []) {
      if (reminder.state === "reminded") list.push({ rule, reminder, open: true });
      else if (reminder.state === "planned") list.push({ rule, reminder, open: false });
    }
  }
  const key = (t: Task) =>
    t.open
      ? (t.reminder.expires_at ?? t.reminder.start)
      : (t.reminder.snoozed_until ?? t.reminder.next_reminder_at ?? t.reminder.start);
  return list.sort((a, b) => Number(b.open) - Number(a.open) || key(a).localeCompare(key(b)));
}

export interface HeadlineLine {
  /** Rendered text, empty when no preview is possible. */
  text: string;
  /** Plural field empty: the singular template is used for bundles. */
  fallback: boolean;
}

type PreviewEvent = { titles: string[]; variables?: Record<string, string> };

/** Preview for the singular headline field: first event with a single match, else the first. */
export function singularHeadlinePreview(
  rule: { headline?: string | null },
  events: PreviewEvent[] | undefined,
): string {
  const event = events?.find((e) => e.titles.length <= 1) ?? events?.[0];
  if (!event) return "";
  const template = rule.headline?.trim();
  return template
    ? renderTemplate(template, event.variables ?? {})
    : reminderTitle({ titles: event.titles, variables: event.variables });
}

/** Preview for the plural field: real bundle > backend `plural_sample` > none. */
export function pluralHeadlinePreview(
  rule: { headline?: string | null; headline_plural?: string | null },
  events: PreviewEvent[] | undefined,
  sample?: PreviewEvent | null,
): HeadlineLine {
  const event =
    events?.find((e) => e.titles.length > 1) ?? (sample?.titles?.length ? sample : undefined);
  if (!event) return { text: "", fallback: false };
  const own = rule.headline_plural?.trim();
  const template = own || rule.headline?.trim();
  const text = template
    ? renderTemplate(template, event.variables ?? {})
    : reminderTitle({ titles: event.titles, variables: event.variables });
  return { text, fallback: !own };
}

/** Rule with a new "finish early" mode (hours keep their last value, default 24). */
export function withEarlyMode(rule: Rule, mode: EarlySetting["mode"]): Rule {
  return { ...rule, early: { mode, hours: rule.early?.hours || 24 } };
}

/** The accordion keeps one step open: opening a step closes the others. */
export function toggleStepOpen(open: ReadonlySet<number>, num: number): Set<number> {
  return open.has(num) ? new Set([...open].filter((n) => n !== num)) : new Set([num]);
}

/** Text of a "too early" answer of the acknowledge service, if there is one. */
export function tooEarlyText(result: unknown): string | undefined {
  const r = result as { response?: { too_early?: unknown }; too_early?: unknown } | null;
  const text = r?.response?.too_early ?? r?.too_early;
  return typeof text === "string" && text ? text : undefined;
}
