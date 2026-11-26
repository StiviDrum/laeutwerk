import { describe, expect, it } from "vitest";
import { emptyRule } from "../src/format";
import { localizer } from "../src/localize";
import { parsePanelPath, panelPath, PANEL_TABS } from "../src/panel-logic";
import { applyNeeds, askedNeeds, setPointer, wizBuild, wizDefaults } from "../src/rule-build";
import { SENTENCE_STEP, ruleTokens, sentenceText } from "../src/rule-sentence";
import type { Rule } from "../src/types";
import { groupWeek, itemsOf, timedRules, triggerRules } from "../src/week-logic";

const de = localizer("de");
const en = localizer("en");

function wiz(over: Partial<ReturnType<typeof wizDefaults>>) {
  return wizBuild({ ...wizDefaults("2026-12-01"), name: " Papier ", ...over }, de);
}

describe("ruleTokens", () => {
  it("calendar rule", () => {
    const r = wiz({ src: "calendar.abfall", kw: "Papier" });
    const t = ruleTokens(r, de, (id) => (id === "calendar.abfall" ? "Abfall" : id));
    const text = sentenceText(t);
    expect(text).toContain(
      "Wenn im Kalender „Abfall“ ein Termin steht (mit „Papier“ im Titel), erinnere ich am Vortag um 17:00 per Push",
    );
    expect(t.filter((x) => x.key).map((x) => x.key)).toEqual([
      "src",
      "kw",
      "when",
      "sig",
      "rep",
      "esc",
      "exp",
      "asg",
      "act",
      "ack",
    ]);
  });
  it("trigger rule", () => {
    const r = wiz({ kind: "dev", dev: "input_select.wm", devTo: "Fertig", rep: true });
    const text = sentenceText(ruleTokens(r, en));
    expect(text).toContain(
      "When input_select.wm changes to “Fertig”, I get in touch immediately via Push",
    );
    expect(text).toContain("I repeat every 30 min (max. 20×)");
    expect(text).toContain("expires: +12h");
  });
  it("interval rule and escalation, assignee, season", () => {
    const r: Rule = {
      ...wiz({ kind: "int", ivN: 12 }),
      escalation: [{ after: "20:00" }, { after: "2h" }],
      assignee: { persons: ["person.a"] },
      activation: { conditions: [{}], season: { from: "04-01", to: "10-31" } },
      acknowledge: [{ type: "tag", tag_id: "x" }],
    };
    const text = sentenceText(ruleTokens(r, de));
    expect(text).toContain("Alle 12 Wochen ab 1.12. erinnere ich um 17:00 per Push");
    expect(text).toContain("eskaliere ich um 20:00 Uhr und nach 2 Std.");
    expect(text).toContain("Zuständig ist person.a");
    expect(text).toContain("nur 01.04 bis 31.10, mit 1 Bedingung(en)");
    expect(text).toContain("Push-Knopf, NFC-Tag");
  });
  it("without calendar, device and timing phrases", () => {
    const r = { ...emptyRule(), reminders: [{ at: "-2h" }, { at: "09:00" }, { at: "-1h" }] };
    const text = sentenceText(ruleTokens(r, de));
    expect(text).toContain("Wenn im gewählten Kalender ein Termin steht (mit beliebigem Titel)");
    expect(text).toContain("2 Stunden vorher und am Termintag um 09:00 und 1 Stunde vorher");
    const dev = wiz({ kind: "dev", dev: "input_select.wm", devTo: "Fertig" });
    expect(sentenceText(ruleTokens(dev, de))).toContain(
      "Wenn input_select.wm auf „Fertig“ wechselt, melde ich mich sofort per Push",
    );
    const cal = { ...wiz({ src: "calendar.a" }), start_triggers: [] };
    expect(sentenceText(ruleTokens(cal, de))).toContain("Wenn im Kalender „calendar.a“");
  });
  it("every piece maps to a group", () => {
    expect(Object.values(SENTENCE_STEP).every((n) => n >= 1 && n <= 7)).toBe(true);
  });
});

describe("wizBuild", () => {
  it("calendar: defaults and one push to all", () => {
    const r = wiz({ src: "calendar.a", kw: "Papier" });
    expect(r.name).toBe("Papier");
    expect(r.id).toBeUndefined();
    expect(r.sources).toEqual(["calendar.a"]);
    expect(r.filter.keywords.rows).toEqual([{ match: "Papier", mode: "contains" }]);
    expect(r.reminders).toEqual([{ at: "-1d 17:00" }]);
    expect(r.lookahead_days).toBe(14);
    expect(r.expire).toBe("event_end");
    expect(r.early).toEqual({ mode: "hours", hours: 24 });
    expect(r.signals).toHaveLength(1);
    expect(r.signals[0]).toMatchObject({
      type: "notify",
      audience: "all",
      title: "{titel}",
      when: "now",
    });
    expect(r.signals[0].actions).toEqual([
      { label: "Erledigt", ack: true },
      { label: "Später", snooze: "1h" },
    ]);
  });
  it("calendar timing variants", () => {
    expect(wiz({ when: "d0", time: "08:30" }).reminders).toEqual([{ at: "08:30" }]);
    expect(wiz({ when: "rb", hrs: 3 }).reminders).toEqual([{ at: "-3h" }]);
  });
  it("device with follow-up: two pushes, repeat, +12h", () => {
    const r = wiz({ kind: "dev", dev: "binary_sensor.x", devTo: "on", rep: true, repMin: 15 });
    expect(r.start_triggers).toEqual([
      { trigger: "state", entity_id: "binary_sensor.x", to: "on" },
    ]);
    expect(r.sources).toEqual([]);
    expect(r.reminders).toEqual([]);
    expect(r.repeat).toEqual({ every: 15, max: 20 });
    expect(r.expire).toBe("+12h");
    expect(r.signals.map((s) => s.send_on)).toEqual(["first", "repeat"]);
    expect(r.signals[1].title).toBe("{titel} wartet {seit}");
    expect(r.signals[1].id).not.toBe(r.signals[0].id);
  });
  it("device without follow-up has one push", () => {
    const r = wiz({ kind: "dev", dev: "binary_sensor.x" });
    expect(r.signals).toHaveLength(1);
    expect(r.repeat).toBe("none");
  });
  it("interval: weeks/days, early always, follow-up daily max 3", () => {
    const r = wiz({ kind: "int", ivN: 2, ivU: "w", rep: true, time: "09:00" });
    expect(r.interval).toEqual({ every: "2w", start: "2026-12-01" });
    expect(r.early?.mode).toBe("always");
    expect(r.repeat).toEqual({ every: "1d", max: 3 });
    expect(r.expire).toBe("+7d");
    expect(wiz({ kind: "int", ivN: 10, ivU: "d" }).interval?.every).toBe(10);
  });
});

describe("template needs", () => {
  const needs = [
    { path: "/start_triggers/0/entity_id", domain: "lock", label: "Lock" },
    {
      path: "/acknowledge/0/trigger/0/entity_id",
      domain: "lock",
      label: "Lock",
      same_as: "/start_triggers/0/entity_id",
    },
  ];
  it("setPointer sets existing paths only", () => {
    const o = { a: [{ b: 1 }] };
    expect(setPointer(o, "/a/0/b", 2)).toBe(true);
    expect(o.a[0].b).toBe(2);
    expect(setPointer(o, "/x/0/b", 2)).toBe(false);
  });
  it("fills answers and same_as", () => {
    const rule: Rule = {
      ...emptyRule(),
      start_triggers: [{ trigger: "state", entity_id: "lock.placeholder" }],
      acknowledge: [
        { type: "trigger", trigger: [{ trigger: "state", entity_id: "lock.placeholder" }] },
      ],
    };
    const out = applyNeeds(rule, needs, { "/start_triggers/0/entity_id": "lock.front" });
    expect(out.start_triggers?.[0].entity_id).toBe("lock.front");
    expect((out.acknowledge[0].trigger as { entity_id: string }[])[0].entity_id).toBe("lock.front");
    expect(rule.start_triggers?.[0].entity_id).toBe("lock.placeholder");
    expect(askedNeeds(needs)).toHaveLength(1);
  });
});

describe("week", () => {
  const rule: Rule = { ...emptyRule(), id: "r", name: "Müll" };
  it("groups passes per day, overdue into today, sorted", () => {
    const passes = [
      {
        at: "2026-12-02T16:00:00Z",
        event_id: "e",
        kind: "first" as const,
        nr: 1,
        stage: null,
        signals: [],
      },
      {
        at: "2026-12-01T07:00:00Z",
        event_id: "e",
        kind: "first" as const,
        nr: 1,
        stage: null,
        signals: [],
      },
      {
        at: "2026-12-01T20:00:00Z",
        event_id: "e",
        kind: "repeat" as const,
        nr: 2,
        stage: null,
        signals: [],
      },
      {
        at: "2026-12-20T20:00:00Z",
        event_id: "e",
        kind: "first" as const,
        nr: 1,
        stage: null,
        signals: [],
      },
    ];
    const events = [{ id: "e", headline: "Morgen: Papier", titles: ["Papier"] }] as never[];
    const items = itemsOf(rule, passes, events);
    const days = groupWeek(items, new Date("2026-12-01T12:00:00Z"), "UTC");
    expect(days).toHaveLength(7);
    expect(days[0].items.map((i) => i.at)).toEqual([
      "2026-12-01T07:00:00Z",
      "2026-12-01T20:00:00Z",
    ]);
    expect(days[0].items[1].followUp).toBe(true);
    expect(days[1].items[0].title).toBe("Morgen: Papier");
    expect(days.flatMap((d) => d.items)).toHaveLength(3);
  });
  it("splits timed and trigger rules", () => {
    const t: Rule = { ...emptyRule(), id: "t", start_triggers: [{ trigger: "time", at: "08:00" }] };
    const off: Rule = { ...rule, id: "o", enabled: false };
    const cal = { ...rule, id: "c", start_triggers: [] };
    expect(timedRules([rule, cal, t, off]).map((r) => r.id)).toEqual(["r", "c"]);
    expect(triggerRules([cal, t]).map((r) => r.id)).toEqual(["t"]);
    expect(timedRules([rule, t, off]).map((r) => r.id)).toEqual(["r"]);
    expect(triggerRules([rule, t, off]).map((r) => r.id)).toEqual(["t"]);
  });
  it("route", () => {
    expect(PANEL_TABS).toContain("week");
    expect(parsePanelPath("/week").tab).toBe("week");
    expect(panelPath("week")).toBe("/week");
  });
});
