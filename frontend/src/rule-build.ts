/** Pure builders of the "new rule" flow: assistant, template placeholders. */
import { emptyRule } from "./format";
import type { Localizer } from "./localize";
import type { Rule, Signal } from "./types";

export type WizKind = "cal" | "dev" | "int";

export interface WizState {
  kind: WizKind;
  name: string;
  /** Calendar entity (kind cal). */
  src: string;
  /** Optional keyword (kind cal). */
  kw: string;
  /** Device entity and target state (kind dev). */
  dev: string;
  devTo: string;
  /** Interval: every N days or weeks, first due day (kind int). */
  ivN: number;
  ivU: "d" | "w";
  ivStart: string;
  /** Calendar: day before / event day / hours before. */
  when: "dm1" | "d0" | "rb";
  time: string;
  hrs: number;
  /** Follow-up: device = every repMin minutes, interval = daily, max 3. */
  rep: boolean;
  repMin: number;
}

export function wizDefaults(today: string): WizState {
  return {
    kind: "cal",
    name: "",
    src: "",
    kw: "",
    dev: "",
    devTo: "",
    ivN: 12,
    ivU: "w",
    ivStart: today,
    when: "dm1",
    time: "17:00",
    hrs: 2,
    rep: false,
    repMin: 30,
  };
}

const num = (n: number, fallback: number): number => (Number.isFinite(n) && n > 0 ? n : fallback);

/** The rule the assistant answers describe (no id: the backend derives it from the name). */
export function wizBuild(w: WizState, l: Localizer): Rule {
  const rule = emptyRule();
  rule.name = w.name.trim();
  rule.lookahead_days = 14;
  rule.early = { mode: "hours", hours: 24 };
  rule.expire = "event_end";
  rule.bundle = true;
  const push = (extra: Partial<Signal> = {}): Signal => ({
    id: "push",
    type: "notify",
    enabled: true,
    when: "now",
    audience: "all",
    title: "{titel}",
    message: "",
    actions: [
      { label: l.t("done"), ack: true },
      { label: l.t("later"), snooze: "1h" },
    ],
    ...extra,
  });
  if (w.kind === "cal") {
    rule.sources = w.src ? [w.src] : [];
    if (w.kw.trim()) {
      rule.filter.keywords.rows = [{ match: w.kw.trim(), mode: "contains" }];
    }
    rule.reminders = [
      {
        at:
          w.when === "dm1"
            ? `-1d ${w.time || "17:00"}`
            : w.when === "d0"
              ? w.time || "08:00"
              : `-${num(w.hrs, 2)}h`,
      },
    ];
    rule.signals = [push()];
  } else if (w.kind === "dev") {
    rule.sources = [];
    rule.reminders = [];
    rule.start_triggers = [
      { trigger: "state", entity_id: w.dev, ...(w.devTo ? { to: w.devTo } : {}) },
    ];
    rule.expire = "+12h";
    rule.bundle = false;
    if (w.rep) {
      rule.repeat = { every: num(w.repMin, 30), max: 20 };
      rule.signals = [
        push({ send_on: "first" }),
        push({ id: "followup", send_on: "repeat", title: l.t("wiz_waiting"), actions: [] }),
      ];
    } else rule.signals = [push()];
  } else {
    rule.sources = [];
    rule.interval = {
      every: w.ivU === "w" ? `${num(w.ivN, 1)}w` : num(w.ivN, 1),
      start: w.ivStart,
    };
    rule.reminders = [{ at: w.time || "09:00" }];
    rule.early = { mode: "always", hours: 24 };
    rule.expire = "+7d";
    rule.repeat = w.rep ? { every: "1d", max: 3 } : "none";
    rule.signals = [push()];
  }
  return rule;
}

export interface TemplateNeed {
  /** JSON pointer into the rule, e.g. "/start_triggers/0/entity_id". */
  path: string;
  domain: string;
  label: string;
  same_as?: string;
}

/** Set a value by JSON pointer ("/a/0/b"), creating nothing: missing parents are skipped. */
export function setPointer(target: unknown, path: string, value: unknown): boolean {
  const keys = path
    .split("/")
    .slice(1)
    .map((k) => k.replace(/~1/g, "/").replace(/~0/g, "~"));
  let node = target as Record<string, unknown> | undefined;
  for (const key of keys.slice(0, -1)) {
    const next = node?.[key];
    if (next === null || typeof next !== "object") return false;
    node = next as Record<string, unknown>;
  }
  if (!node || !keys.length) return false;
  node[keys[keys.length - 1]] = value;
  return true;
}

/** Needs that ask the user (a need with `same_as` copies another answer). */
export const askedNeeds = (needs: TemplateNeed[]): TemplateNeed[] =>
  needs.filter((n) => !n.same_as);

/** Copy of the rule with the answered entities filled in (`same_as` follows its target). */
export function applyNeeds(
  rule: Rule,
  needs: TemplateNeed[],
  answers: Record<string, string>,
): Rule {
  const next = structuredClone(rule);
  for (const need of needs) {
    const value = answers[need.same_as ?? need.path];
    if (value) setPointer(next, need.path, value);
  }
  return next;
}
