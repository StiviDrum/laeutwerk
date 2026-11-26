import { describe, expect, it } from "vitest";
import { countSince, groupByDay, ruleStats, shortDuration } from "../src/event-log";
import { currentPerson, snoozeChoices } from "../src/snooze";
import type { HomeAssistant, LogEvent } from "../src/types";

const ev = (ts: string, kind: LogEvent["kind"], rid = "r1", rule = "a"): LogEvent => ({
  ts,
  kind,
  rule_id: rule,
  reminder_id: rid,
});

describe("snoozeChoices", () => {
  const ids = (iso: string, person?: string) =>
    snoozeChoices(new Date(iso), "Europe/Berlin", person).map((c) => c.id);
  it("offers tonight only before 18:00 local time", () => {
    expect(ids("2026-11-26T15:00:00Z")).toContain("evening"); // 16:00 local
    expect(ids("2026-11-26T17:00:00Z")).not.toContain("evening"); // 18:00 local
  });
  it("offers until-home only with a person", () => {
    expect(ids("2026-11-26T10:00:00Z")).not.toContain("home");
    const all = snoozeChoices(new Date(), "Europe/Berlin", "person.s");
    const last = all[all.length - 1];
    expect(last?.data).toEqual({ until_home: "person.s" });
  });
  it("finds the person of the logged in user", () => {
    const hass = {
      user: { id: "u1" },
      states: {
        "person.a": { entity_id: "person.a", state: "home", attributes: { user_id: "u2" } },
        "person.b": { entity_id: "person.b", state: "home", attributes: { user_id: "u1" } },
      },
    } as unknown as HomeAssistant;
    expect(currentPerson(hass)).toBe("person.b");
    expect(currentPerson(undefined)).toBeUndefined();
  });
});

describe("event log aggregation", () => {
  const events = [
    ev("2026-11-25T17:00:00Z", "reminded", "x"),
    ev("2026-11-25T17:30:00Z", "repeated", "x"),
    ev("2026-11-25T18:00:00Z", "acknowledged", "x"),
    ev("2026-11-26T17:00:00Z", "reminded", "y"),
    ev("2026-11-26T19:00:00Z", "acknowledged", "y"),
    ev("2026-11-26T09:00:00Z", "reminded", "z"),
    ev("2026-11-26T12:00:00Z", "missed", "z"),
  ];
  it("counts and averages per rule", () => {
    expect(ruleStats(events).a).toEqual({ acknowledged: 2, missed: 1, avgOpenMinutes: 90 });
  });
  it("groups newest first by local day", () => {
    const g = groupByDay(events, "Europe/Berlin");
    expect(g.map((x) => x.day)).toEqual(["2026-11-26", "2026-11-25"]);
    expect(g[0].events[0].ts).toBe("2026-11-26T19:00:00Z");
  });
  it("counts since an instant", () => {
    expect(countSince(events, Date.parse("2026-11-26T00:00:00Z"))).toEqual({
      acknowledged: 1,
      missed: 1,
    });
  });
  it("formats durations", () => {
    expect(shortDuration(5)).toBe("5 min");
    expect(shortDuration(130)).toBe("2 h 10 min");
    expect(shortDuration(60 * 72)).toBe("3 d");
  });
});
