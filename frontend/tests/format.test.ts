import { describe, expect, it } from "vitest";
import {
  availableVariables,
  buildOverview,
  dayDiff,
  defaultSignal,
  describeTimespec,
  emptyRule,
  finishedLine,
  openStatus,
  relativeDay,
  reminderTitle,
  renameColumn,
  renderTemplate,
  signalSummary,
} from "../src/format";
import { localizer } from "../src/localize";
import type { Reminder, Rule } from "../src/types";

const TZ = "Europe/Berlin";
const de = localizer("de");
const en = localizer("en-GB");
// Monday 16 Nov 2026, 18:00 in Berlin
const NOW = new Date("2026-11-16T17:00:00Z");

function reminder(changes: Partial<Reminder> = {}): Reminder {
  return {
    id: "muell__20261117",
    rule_id: "muell",
    day: "2026-11-17",
    start: "2026-11-16T23:00:00+00:00",
    end: "2026-11-17T23:00:00+00:00",
    state: "reminded",
    titles: ["Papier", "Bio"],
    variables: { wann: "morgen" },
    reminded_at: "2026-11-16T16:00:00+00:00",
    finished_at: null,
    acknowledged_by: null,
    acknowledged_via: null,
    snoozed_until: null,
    ...changes,
  };
}

function rule(changes: Partial<Rule> = {}): Rule {
  return {
    ...emptyRule(),
    id: "muell",
    name: "Müll rausstellen",
    sources: ["calendar.abfall"],
    filter: {
      all_day: true,
      keywords: {
        columns: ["tonne", "farbe"],
        rows: [{ match: "Papier", tonne: "Papiertonne", farbe: "blau" }],
      },
    },
    ...changes,
  };
}

describe("days and times", () => {
  it("counts calendar days in the home time zone", () => {
    // 23:30 UTC on Monday is already Tuesday in Berlin
    expect(dayDiff(new Date("2026-11-16T23:30:00Z"), NOW, TZ)).toBe(1);
    expect(dayDiff(new Date("2026-11-16T22:30:00Z"), NOW, TZ)).toBe(0);
    // across the DST change (25 h day)
    expect(dayDiff(new Date("2026-10-26T10:00:00Z"), new Date("2026-10-25T10:00:00Z"), TZ)).toBe(1);
  });

  it("describes days relative to now", () => {
    expect(relativeDay("2026-11-16T23:00:00Z", NOW, de, TZ)).toBe("morgen");
    expect(relativeDay("2026-11-16T10:00:00Z", NOW, de, TZ)).toBe("heute");
    expect(relativeDay("2026-11-15T10:00:00Z", NOW, en, TZ)).toBe("yesterday");
    expect(relativeDay("2026-11-19T10:00:00Z", NOW, de, TZ)).toBe("Do");
    expect(relativeDay("2026-11-30T10:00:00Z", NOW, de, TZ)).toBe("30.11.");
  });

  it("describes reminder times", () => {
    expect(describeTimespec("-1d 17:00", de)).toBe("Vortag 17:00");
    expect(describeTimespec("-7d 9:00", de)).toBe("7 Tage vorher 09:00");
    expect(describeTimespec("event_day 12:00", de)).toBe("am Tag 12:00");
    expect(describeTimespec("09:00", en)).toBe("on the day 09:00");
    expect(describeTimespec("-2h", de)).toBe("2 h vorher");
    expect(describeTimespec("-30m", en)).toBe("30 min before");
    expect(describeTimespec("event_end", de)).toBe("Terminende");
    expect(describeTimespec("whatever", de)).toBe("whatever");
  });
});

describe("reminder texts", () => {
  it("builds the title and the status chip", () => {
    expect(reminderTitle(reminder())).toBe("Morgen: Papier + Bio");
    expect(reminderTitle({ titles: ["Anna"] })).toBe("Anna");
    expect(openStatus(reminder(), NOW, de, TZ)).toBe("erinnert 17:00");
    expect(openStatus(reminder({ reminded_at: "2026-11-15T16:00:00Z" }), NOW, de, TZ)).toBe(
      "fällig seit gestern",
    );
  });

  it("describes finished reminders", () => {
    const done = reminder({
      state: "done",
      finished_at: "2026-11-16T19:41:00Z",
      acknowledged_by: "Steven",
      acknowledged_via: "tag",
    });
    expect(finishedLine(done, NOW, de, TZ)).toBe("erledigt von Steven · heute 20:41 · NFC-Tag");
    expect(
      finishedLine({ ...done, acknowledged_by: null, acknowledged_via: null }, NOW, en, TZ),
    ).toBe("done · today 20:41");
    expect(finishedLine({ ...done, state: "missed" }, NOW, de, TZ)).toBe("verpasst · heute 20:41");
  });

  it("renders templates like the backend", () => {
    const vars = { wann: "morgen", tonnen: "Papiertonne und Biotonne" };
    expect(renderTemplate("{wann}: {tonnen}", vars)).toBe("Morgen: Papiertonne und Biotonne");
    expect(renderTemplate("bitte {wann} {unbekannt}", vars)).toBe("bitte morgen {unbekannt}");
    expect(renderTemplate("{{ jinja }} {wann}", vars)).toBe("{{ jinja }} morgen");
    expect(renderTemplate(undefined, vars)).toBe("");
  });
});

describe("overview", () => {
  it("sorts reminders into open, upcoming and done (today only)", () => {
    const rules: Rule[] = [
      rule({
        status: {
          state: "reminded",
          current: null,
          errors: {},
          next_event: null,
          reminders: [
            reminder(),
            reminder({ id: "b", state: "planned", start: "2026-11-23T23:00:00Z" }),
            reminder({ id: "c", state: "done", finished_at: "2026-11-16T08:00:00Z" }),
            reminder({ id: "d", state: "done", finished_at: "2026-11-15T08:00:00Z" }),
          ],
        },
      }),
      rule({
        id: "kult",
        status: {
          state: "planned",
          current: null,
          errors: {},
          next_event: null,
          reminders: [
            reminder({ id: "e", rule_id: "kult", state: "planned", start: "2026-11-18T18:00:00Z" }),
          ],
        },
      }),
    ];
    const o = buildOverview(rules, NOW, TZ);
    expect(o.open.map((x) => x.reminder.id)).toEqual(["muell__20261117"]);
    expect(o.upcoming.map((x) => x.reminder.id)).toEqual(["e", "b"]);
    expect(o.done.map((x) => x.reminder.id)).toEqual(["c"]);
    expect(buildOverview(rules, NOW, TZ, ["kult"]).upcoming.map((x) => x.reminder.id)).toEqual([
      "e",
    ]);
  });
});

describe("rule editing", () => {
  it("offers columns with plurals and the fixed variables", () => {
    const vars = availableVariables(rule());
    expect(vars.slice(0, 4)).toEqual(["tonne", "tonnen", "farbe", "farben"]);
    expect(vars).toContain("wann");
    expect(vars).not.toContain("person");
    expect(availableVariables(rule(), true)).toContain("person");
  });

  it("renames a column in rows and signals", () => {
    const r = rule({
      signals: [{ ...defaultSignal("light_signal", rule()), color_from: "farbe" }],
    });
    const next = renameColumn(r, 1, " Colour ");
    expect(next.filter.keywords.columns).toEqual(["tonne", "colour"]);
    expect(next.filter.keywords.rows[0]).toEqual({
      match: "Papier",
      tonne: "Papiertonne",
      colour: "blau",
    });
    expect(next.signals[0].color_from).toBe("colour");
    // the original is untouched
    expect(r.filter.keywords.columns).toEqual(["tonne", "farbe"]);
  });

  it("creates signals with useful defaults", () => {
    const push = defaultSignal("notify", rule({ ack_label: "Steht draußen" }));
    expect(push.title).toBe("{wann}: {tonnen}");
    expect(push.actions).toEqual([{ ack: true, label: "Steht draußen" }]);
    expect(push.audience).toBe("present");
    expect(defaultSignal("light_signal", rule()).color_from).toBe("farbe");
    expect(defaultSignal("announce", emptyRule()).text).toBe("{wann}: {titel}");
  });

  it("summarises signals", () => {
    const lamp = {
      ...defaultSignal("light_signal", rule()),
      when: { opportunity: [], manual_only: true },
      quiet: [{ from: "00:00", to: "10:00", mode: "skip" as const }],
    };
    expect(signalSummary(lamp, de)).toBe("bei Gelegenheit · blinken 3× · max. 1× · nicht 0–10 Uhr");
    const push = {
      ...defaultSignal("notify", rule()),
      audience: undefined,
      targets: ["notify.mobile_app_steven"],
    };
    expect(signalSummary(push, en)).toBe("immediately · to steven");
  });
});

describe("0.6 helpers", () => {
  it("builds a rule from a template and checks completeness", async () => {
    const { ruleFromTemplate, ruleComplete } = await import("../src/format");
    const rule = ruleFromTemplate({
      rule: { name: "Filter tauschen", interval: { every: 90 }, reminders: [{ at: "18:00" }] },
    });
    expect(rule.sources).toEqual([]);
    expect(rule.filter.keywords.rows).toEqual([]);
    expect(rule.enabled).toBe(true);
    expect(ruleComplete(rule)).toBe(true); // interval instead of a source
    expect(ruleComplete({ ...rule, interval: null })).toBe(false);
    expect(ruleComplete({ ...rule, interval: null, sources: ["todo.x"] })).toBe(true);
    expect(ruleComplete({ ...rule, name: " " })).toBe(false);
  });

  it("offers {zustaendig} with responsible persons and summarises stages", () => {
    const withAssignee = rule({ assignee: { persons: ["person.steven"] } });
    expect(availableVariables(withAssignee)).toContain("zustaendig");
    expect(availableVariables(rule())).not.toContain("zustaendig");
    const ansage = { ...defaultSignal("announce", rule()), stage: 2 };
    expect(signalSummary(ansage, de)).toBe("sofort · Stufe 2 · max. 1×");
    const toAssignee = { ...defaultSignal("notify", rule()), audience: "assignee" as const };
    expect(signalSummary(toAssignee, de)).toBe("sofort · an Zuständige");
  });
});
