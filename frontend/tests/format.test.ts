import { describe, expect, it, vi } from "vitest";
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
  timeSamples,
  withMinAge,
  withSendOn,
  sendOnLabel,
  expireForMode,
  renameColumn,
  renderTemplate,
  signalSummary,
  signalTitle,
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
    const push = defaultSignal("notify", rule(), "Erledigt");
    expect(push.title).toBe("{wann}: {tonnen}");
    expect(push.actions).toEqual([{ ack: true, label: "Erledigt" }]);
    expect(push.audience).toBe("present");
    expect(defaultSignal("light_signal", rule()).color_from).toBe("farbe");
    expect(defaultSignal("announce", emptyRule()).text).toBe("{wann}: {titel}");
  });

  it("summarises signals", () => {
    const lamp = {
      ...defaultSignal("light_signal", rule()),
      when: { opportunity: [], manual_only: true },
      limit: { per_reminder: 1 },
      quiet: [{ from: "00:00", to: "10:00", mode: "skip" as const }],
    };
    expect(signalSummary(lamp, de)).toBe("bei Gelegenheit · blinken 3× · max. 1× · nicht 0–10 Uhr");
    const push = {
      ...defaultSignal("notify", rule()),
      audience: undefined,
      targets: ["notify.mobile_app_steven"],
    };
    expect(signalSummary(push, en)).toBe("immediately");
    expect(signalTitle(push, en)).toBe("Push · mobile_app_steven");
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
    const ansage = { ...defaultSignal("announce", rule()), send_on: "stage" as const, stage: 2 };
    expect(signalSummary(ansage, de)).toBe("sofort · Stufe 2");
    const toAssignee = { ...defaultSignal("notify", rule()), audience: "assignee" as const };
    expect(signalSummary(toAssignee, de)).toBe("sofort");
    expect(signalTitle(toAssignee, de)).toBe("Push · Zuständige");
  });
});

describe("push recipients", () => {
  it("summarises chosen persons, also only when home", () => {
    const base = { ...defaultSignal("notify", rule()), persons: ["person.steven", "person.anna"] };
    const names = (id: string) => ({ "person.steven": "Steven", "person.anna": "Anna" })[id] ?? id;
    expect(signalTitle({ ...base, audience: "persons" }, de, names)).toBe("Push · Steven, Anna");
    expect(signalTitle({ ...base, audience: "persons", only_present: true }, de, names)).toBe(
      "Push · Steven, Anna (nur Anwesende)",
    );
  });
});

describe("columns with switchable plural", () => {
  it("reads both forms and stores the short one by default", async () => {
    const { colName, colPlural, makeColumn } = await import("../src/format");
    expect(colName("tonne")).toBe("tonne");
    expect(colPlural("tonne")).toBe("tonnen");
    expect(colPlural({ name: "artikel", plural: false })).toBeNull();
    expect(colPlural({ name: "tonne", plural: "tonnen_liste" })).toBe("tonnen_liste");
    expect(colPlural({ name: "farbe", plural: true })).toBe("farben");
    expect(makeColumn("tonne", "tonnen")).toBe("tonne");
    expect(makeColumn("artikel", null)).toEqual({ name: "artikel", plural: false });
  });

  it("toggles, renames and offers variables accordingly", async () => {
    const { setColumnPlural } = await import("../src/format");
    const r = rule({
      filter: {
        all_day: true,
        keywords: {
          columns: ["tonne", { name: "artikel", plural: false }],
          rows: [{ match: "Papier", tonne: "Papiertonne", artikel: "die" }],
        },
      },
    });
    expect(availableVariables(r).slice(0, 3)).toEqual(["tonne", "tonnen", "artikel"]);
    const off = setColumnPlural(r, 0, false);
    expect(off.filter.keywords.columns[0]).toEqual({ name: "tonne", plural: false });
    expect(availableVariables(off)).not.toContain("tonnen");
    expect(setColumnPlural(off, 0, true).filter.keywords.columns[0]).toBe("tonne");

    // Renaming keeps the setting: default follows the name, off stays off.
    const renamed = renameColumn(renameColumn(r, 0, "behaelter"), 1, "art");
    expect(renamed.filter.keywords.columns).toEqual(["behaelter", { name: "art", plural: false }]);
    expect(renamed.filter.keywords.rows[0]).toEqual({
      match: "Papier",
      behaelter: "Papiertonne",
      art: "die",
    });
    const own = rule({
      filter: {
        all_day: true,
        keywords: { columns: [{ name: "tonne", plural: "liste" }], rows: [] },
      },
    });
    expect(renameColumn(own, 0, "behaelter").filter.keywords.columns).toEqual([
      { name: "behaelter", plural: "liste" },
    ]);
    // New signals use the plural only if there is one.
    expect(defaultSignal("announce", off).text).toBe("{wann}: {tonne}");
  });
});

describe("tag ids with variables", () => {
  it("offers columns, finds variables and keeps only valid tags for the preview", async () => {
    const { tagVariables, templateVariables, validTagAcks, renderTemplate } =
      await import("../src/format");
    const r = rule({
      filter: {
        all_day: true,
        keywords: { columns: ["tonne", { name: "nfc", plural: false }], rows: [] },
      },
      acknowledge: [
        { type: "tag", tag_id: "{nfc}" },
        { type: "tag", tag_id: "{chip}" },
        { type: "tag", tag_id: "haustuer" },
        { type: "notify_action" },
      ],
    });
    expect(tagVariables(r).slice(0, 3)).toEqual(["tonne", "tonnen", "nfc"]);
    expect(tagVariables(r)).not.toContain("wann");
    expect(templateVariables("tonne_{nfc}_{x}")).toEqual(["nfc", "x"]);
    expect(validTagAcks(r)).toEqual([
      { type: "tag", tag_id: "{nfc}" },
      { type: "tag", tag_id: "haustuer" },
    ]);
    // Tag ids are identifiers: no capital first letter.
    expect(renderTemplate("{nfc}", { nfc: "restmuelltonne" }, false)).toBe("restmuelltonne");
  });
});

describe("0.7 editor helpers", () => {
  it("summarises collapsed steps", async () => {
    const { stepSummary } = await import("../src/format");
    const r = rule({
      reminders: [{ at: "-1d 17:00" }],
      signals: [
        defaultSignal("notify", rule()),
        { ...defaultSignal("light_signal", rule()), enabled: false },
      ],
      acknowledge: [{ type: "tag", tag_id: "{nfc}" }],
      expire: "event_day 12:00",
    });
    expect(stepSummary(r, 1, de, () => "Abfallkalender")).toBe("Abfallkalender");
    expect(stepSummary(r, 2, de)).toBe("1 Stichwörter · nur Ganztags");
    expect(stepSummary(r, 3, de)).toBe("Vortag 17:00");
    expect(stepSummary(r, 4, de)).toBe("Push");
    expect(stepSummary(r, 5, de)).toBe("Push-Knopf, 1 NFC-Tag(s)");
    expect(stepSummary(r, 6, de)).toBe("gebündelt · Verfällt: Termintag 12:00");
    expect(stepSummary(r, 7, de)).toBe("–");
    expect(stepSummary({ ...r, sources: [], interval: { every: 90 } }, 1, de)).toBe(
      "alle 90 Tage nach Erledigen",
    );
  });

  it("finds what is missing before saving", async () => {
    const { ruleProblems } = await import("../src/format");
    expect(ruleProblems(rule(), de)).toEqual([]);
    const broken = rule({
      name: " ",
      sources: [],
      reminders: [],
      signals: [{ type: "notify", enabled: true, when: "now", message: "" }],
      acknowledge: [{ type: "tag", tag_id: "" }],
      activation: { conditions: [], season: { from: "04-01", to: "" } },
    });
    expect(ruleProblems(broken, de).map((p) => p.step)).toEqual([1, 1, 3, 4, 4, 5, 7]);
    expect(ruleProblems(broken, de)[3].text).toBe("Push: wähle mindestens einen Empfänger.");
  });

  it("maps server messages to steps and plain words", async () => {
    const { errorStep, translateError } = await import("../src/format");
    expect(errorStep("length of value must be at least 1 at 'assignee.persons'")).toBe(7);
    expect(errorStep("invalid time 'x' at 'reminders[0].at'")).toBe(3);
    expect(errorStep("signal 'push': unknown")).toBe(4);
    expect(errorStep("acknowledge 1: unknown variable(s) {x} in tag_id")).toBe(5);
    expect(errorStep("something else")).toBeUndefined();
    expect(translateError("length of value must be at least 1 at 'x'", de)).toBe(
      "Eine Liste braucht mindestens einen Eintrag.",
    );
    expect(translateError("totally new", de)).toBe("totally new");
  });
});

describe("compact card: next task and done label", () => {
  it("puts reminding tasks first (soonest expiry), then planned ones", async () => {
    const { tasks } = await import("../src/format");
    const r1 = rule({
      id: "muell",
      status: {
        state: "reminded",
        current: null,
        errors: {},
        next_event: null,
        reminders: [
          reminder({ id: "a", state: "planned", next_reminder_at: "2026-11-20T16:00:00Z" }),
          reminder({ id: "b", state: "reminded", expires_at: "2026-11-17T11:00:00Z" }),
          reminder({ id: "c", state: "done" }),
        ],
      },
    });
    const r2 = rule({
      id: "kult",
      status: {
        state: "reminded",
        current: null,
        errors: {},
        next_event: null,
        reminders: [
          reminder({
            id: "d",
            rule_id: "kult",
            state: "reminded",
            expires_at: "2026-11-16T22:00:00Z",
          }),
          reminder({
            id: "e",
            rule_id: "kult",
            state: "planned",
            next_reminder_at: "2026-11-18T19:00:00Z",
          }),
        ],
      },
    });
    expect(tasks([r1, r2]).map((t) => [t.reminder.id, t.open])).toEqual([
      ["d", true],
      ["b", true],
      ["e", false],
      ["a", false],
    ]);
    expect(tasks([r1, r2], ["muell"]).map((t) => t.reminder.id)).toEqual(["b", "a"]);
    expect(tasks([])).toEqual([]);
  });

  it("labels done with the push button text, else the old field, else Erledigt", async () => {
    const { doneLabel } = await import("../src/format");
    const push = {
      ...defaultSignal("notify", rule()),
      actions: [{ ack: true, label: "Steht draußen" }],
    };
    expect(doneLabel(rule({ signals: [push] }), de)).toBe("Steht draußen");
    expect(doneLabel(rule({ ack_label: "Gratuliert" }), de)).toBe("Gratuliert");
    expect(doneLabel(rule(), de)).toBe("Erledigt");
  });
});

describe("tasks done ahead of time", () => {
  it("lists them with today's done ones and offers undo while not expired", async () => {
    const { canReopen, doneTasks, isAhead } = await import("../src/format");
    const ahead = reminder({
      id: "ahead",
      state: "done",
      start: "2026-11-23T23:00:00Z",
      expires_at: "2026-11-24T11:00:00Z",
      finished_at: "2026-11-14T08:00:00Z", // done days ago, event next week
    });
    const today = reminder({
      id: "today",
      state: "done",
      finished_at: "2026-11-16T08:00:00Z",
      expires_at: "2026-11-17T11:00:00Z",
    });
    const expired = reminder({
      id: "old",
      state: "done",
      finished_at: "2026-11-10T08:00:00Z",
      expires_at: "2026-11-11T11:00:00Z",
    });
    const missed = reminder({ id: "missed", state: "missed", expires_at: "2026-11-20T11:00:00Z" });
    const r = rule({
      status: {
        state: "done",
        current: null,
        errors: {},
        next_event: null,
        reminders: [ahead, today, expired, missed],
      },
    });
    expect(canReopen(ahead, NOW)).toBe(true);
    expect(canReopen(expired, NOW)).toBe(false);
    expect(canReopen(missed, NOW)).toBe(false);
    expect(isAhead(ahead, NOW)).toBe(true);
    expect(isAhead(today, NOW)).toBe(true); // event tomorrow, done today
    // Overview: done today (incl. ahead) and done ahead earlier; not expired ones.
    expect(buildOverview([r], NOW, TZ).done.map((x) => x.reminder.id)).toEqual(["today", "ahead"]);
    expect(doneTasks([r], NOW).map((t) => t.reminder.id)).toEqual(["today", "ahead"]);
    expect(doneTasks([r], NOW, ["other"])).toEqual([]);
  });
});

describe("signal titles and stage colours", () => {
  it("names the lamps, speakers and entities of a signal", async () => {
    const { signalTitle, stageColor } = await import("../src/format");
    const names = (id: string) =>
      ({ "light.stehleuchte": "Stehleuchte", "media_player.sonos": "Sonos Wohnzimmer" })[id] ?? id;
    const lamp = { ...defaultSignal("light_signal", rule()), entities: ["light.stehleuchte"] };
    expect(signalTitle(lamp, de, names)).toBe("Licht · Stehleuchte");
    const announce = { ...defaultSignal("announce", rule()), players: ["media_player.sonos"] };
    expect(signalTitle(announce, de, names)).toBe("Ansage · Sonos Wohnzimmer");
    const action = {
      ...defaultSignal("action", rule()),
      actions: [
        { action: "light.turn_on", target: { entity_id: ["light.stehleuchte", "{{ x }}"] } },
        { action: "script.turn_on", entity_id: "script.muell" },
      ],
    };
    expect(signalTitle(action, de, names)).toBe("Eigene · Stehleuchte, script.muell");
    expect(signalTitle(defaultSignal("action", rule()), de)).toBe("Eigene");

    const staged = rule({ escalation: [{ after: "2h", color: "#123456" }, { after: "21:30" }] });
    expect(stageColor(staged, 0)).toBeNull();
    expect(stageColor(staged, undefined)).toBeNull();
    expect(stageColor(staged, 1)).toBe("#123456");
    expect(stageColor(staged, 2)).toBe("#ff5a6e"); // default for stage 2
  });
});

describe("hidden rules", () => {
  it("skips visible=false rules in the overview", () => {
    const mk = (id: string, visible?: boolean) => ({
      ...emptyRule(),
      id,
      visible,
      status: {
        reminders: [{ id, state: "reminded", start: "2026-01-01T10:00:00Z", titles: ["x"] }],
      },
    });
    const rules = [mk("a"), mk("b", false), mk("c", true)] as never;
    const o = buildOverview(rules, new Date("2026-01-01T09:00:00Z"));
    expect(o.open.map((i) => i.rule.id)).toEqual(["a", "c"]);
  });
});

describe("source modes and substitute", () => {
  it("keeps exactly one source", async () => {
    const { keepOnlySource, sourceModeOf, assigneeText } = await import("../src/format");
    const base = {
      ...emptyRule(),
      sources: ["calendar.a"],
      interval: { every: 30 },
      start_triggers: [{ trigger: "state" }],
    };
    const cal = keepOnlySource(base, "calendar");
    expect(cal.sources).toEqual(["calendar.a"]);
    expect(cal.interval).toBeNull();
    expect(cal.start_triggers).toBeUndefined();
    const trig = keepOnlySource(base, "trigger");
    expect(trig.sources).toEqual([]);
    expect(trig.interval).toBeNull();
    expect(trig.expire).toBe("+12h");
    expect(sourceModeOf(trig)).toBe("trigger");
    const iv = keepOnlySource(base, "interval");
    expect(iv.sources).toEqual([]);
    expect(iv.start_triggers).toBeUndefined();
    expect(iv.interval).toEqual({ every: 30 });
    expect(sourceModeOf(iv)).toBe("interval");
    const loaded = { ...emptyRule(), sources: ["calendar.a"], start_triggers: [] };
    expect(sourceModeOf(loaded)).toBe("calendar");
    expect(assigneeText(de, "Alida", "Steven")).toBe("Alida (Vertretung für Steven)");
    expect(assigneeText(en, "Alida")).toBe("Alida");
  });
});

describe("0.9.2 helpers", () => {
  it("early mode keeps hours, default 24", async () => {
    const { withEarlyMode, emptyRule } = await import("../src/format");
    const r = emptyRule();
    expect(withEarlyMode(r, "off").early).toEqual({ mode: "off", hours: 24 });
    const h = { ...r, early: { mode: "hours" as const, hours: 48 } };
    expect(withEarlyMode(h, "always").early).toEqual({ mode: "always", hours: 48 });
    expect(withEarlyMode({ ...r, early: undefined }, "hours").early?.hours).toBe(24);
  });
  it("accordion keeps one step open", async () => {
    const { toggleStepOpen } = await import("../src/format");
    expect([...toggleStepOpen(new Set([1]), 3)]).toEqual([3]);
    expect([...toggleStepOpen(new Set([3]), 3)]).toEqual([]);
  });
  it("too_early text from the service response", async () => {
    const { tooEarlyText } = await import("../src/format");
    expect(tooEarlyText({ response: { too_early: "Erst morgen." } })).toBe("Erst morgen.");
    expect(tooEarlyText({ response: { too_early: null } })).toBeUndefined();
    expect(tooEarlyText(undefined)).toBeUndefined();
    expect(tooEarlyText({})).toBeUndefined();
  });
});

describe("0.10.0 helpers", () => {
  it("time samples", () => {
    expect(timeSamples(de)).toMatchObject({ seit_min: "25", erinnert_um: "19:42", nr: "1" });
  });
  it("send_on: stage needs a stage, other modes drop stage fields", () => {
    const base = defaultSignal("notify", emptyRule());
    expect("send_on" in base).toBe(false);
    const staged = withSendOn({ ...base, stage_repeat: true }, "stage");
    expect(staged).toMatchObject({ send_on: "stage", stage: 1 });
    expect("stage_repeat" in staged).toBe(false);
    const first = withSendOn({ ...staged, stage_repeat: true }, "first");
    expect(first.send_on).toBe("first");
    expect("stage" in first || "stage_repeat" in first).toBe(false);
    expect("send_on" in withSendOn(first, "all")).toBe(false);
  });
  it("expire never toggle", () => {
    expect(expireForMode(true)).toBe("never");
    expect(expireForMode(false)).toBe("+12h");
  });
  it("send_on summary and limits only for opportunities", () => {
    const base = defaultSignal("announce", emptyRule());
    expect(sendOnLabel({ ...base, send_on: "first" }, de)).toBe("nur erste");
    expect(sendOnLabel({ ...base, send_on: "repeat" }, de)).toBe("ab 2.");
    expect(sendOnLabel({ ...base, send_on: "stage", stage: 1 }, de)).toBe("Stufe 1");
    const opp = { ...base, when: { opportunity: [] }, send_on: "stage" as const, stage: 1 };
    expect(sendOnLabel(opp, de)).toBe("ab Stufe 1");
    expect(base.limit).toBeUndefined();
    expect(signalSummary({ ...opp, limit: { per_reminder: 1 } }, de)).toContain("max. 1×");
    expect(signalSummary({ ...base, limit: { per_reminder: 1 } }, de)).not.toContain("max.");
  });
  it("min_age is set and removed on a stage", () => {
    const stage = withMinAge<{ after: string; min_age?: string }>({ after: "10:00" }, " 8h ");
    expect(stage).toEqual({ after: "10:00", min_age: "8h" });
    expect(withMinAge(stage, "")).toEqual({ after: "10:00" });
  });
  it("offers the time variables", () => {
    expect(availableVariables(emptyRule())).toEqual(
      expect.arrayContaining(["seit", "seit_min", "erinnert_um", "nr"]),
    );
  });
});

describe("overlay host and trigger summaries", () => {
  it("falls back to body without home-assistant", async () => {
    const { overlayHost } = await import("../src/overlay-host");
    const body = {};
    vi.stubGlobal("document", { body, querySelector: () => null });
    expect(overlayHost()).toBe(body);
    vi.stubGlobal("document", { body, querySelector: () => ({ shadowRoot: "sr" }) });
    expect(overlayHost()).toBe("sr");
    vi.unstubAllGlobals();
  });
  it("summarises trigger rules without calendar info", async () => {
    const { stepSummary } = await import("../src/format");
    const r = rule({ start_triggers: [{ trigger: "state" }], reminders: [{ at: "-1d 17:00" }] });
    expect(stepSummary(r, 3, de)).toBe("einmal");
    expect(stepSummary({ ...r, repeat: { every: 30, max: 6 } }, 3, de)).toBe(
      "alle 30 Min., max. 6×",
    );
    expect(stepSummary(r, 6, de)).toBe("Verfällt: Terminende");
  });
});
