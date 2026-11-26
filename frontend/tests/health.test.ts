import { describe, expect, it } from "vitest";
import { earliestOffsetDays, healthOf } from "../src/health";
import { PANEL_TABS, panelPath, parsePanelPath } from "../src/panel-logic";
import type { Rule, Signal } from "../src/types";

const push = (over: Partial<Signal> = {}): Signal =>
  ({ type: "notify", enabled: true, when: "now", audience: "present", ...over }) as Signal;

const rule = (over: Partial<Rule> = {}): Rule =>
  ({
    id: "r",
    name: "R",
    enabled: true,
    sources: ["calendar.a"],
    filter: { all_day: false, keywords: { columns: [], rows: [{ match: "Papier" }] } },
    reminders: [{ at: "-1d 17:00" }],
    signals: [push()],
    acknowledge: [],
    bundle: true,
    expire: "event_day 12:00",
    ...over,
  }) as Rule;

const hass = (states: Record<string, string>) => ({
  states: Object.fromEntries(
    Object.entries(states).map(([k, v]) => [k, { entity_id: k, state: v, attributes: {} }]),
  ),
});
const codes = (items: { code: string }[]) => items.map((i) => i.code);

describe("healthOf", () => {
  const ok = hass({ "calendar.a": "off" });
  const events = [{ titles: ["Papier"], days_until: 3 }];

  it("is healthy for a good rule", () => {
    expect(healthOf(rule(), ok, { events })).toEqual([]);
  });
  it("flags missing and unavailable entities", () => {
    const r = rule({
      signals: [push({ audience: undefined, persons: ["person.x"], targets: [] })],
    });
    const items = healthOf(r, hass({ "calendar.a": "unavailable", "person.x": "home" }));
    expect(items.map((i) => [i.severity, i.code])).toEqual([["warning", "unavailable_entity"]]);
    expect(codes(healthOf(r, hass({})))).toEqual(["missing_entity", "missing_entity"]);
  });
  it("finds entities in triggers, conditions and actions", () => {
    const r = rule({
      acknowledge: [
        { type: "trigger", trigger: { trigger: "state", entity_id: "binary_sensor.t" } },
      ],
      signals: [
        push({
          when: { opportunity: { trigger: "state", entity_id: ["light.a", "light.{x}"] } },
          conditions: [{ condition: "state", entity_id: "input_boolean.b", state: "on" }],
        }),
      ],
    });
    const missing = healthOf(r, ok)
      .filter((i) => i.code === "missing_entity")
      .map((i) => i.params.entity);
    expect(missing.sort()).toEqual(["binary_sensor.t", "input_boolean.b", "light.a"]);
  });
  it("warns without events in the lookahead, info for unused keywords", () => {
    const items = healthOf(rule(), ok, { events: [{ titles: ["Bio"], days_until: 40 }] });
    expect(items.map((i) => [i.severity, i.code])).toEqual([
      ["warning", "no_events"],
      ["info", "keyword_unused"],
    ]);
    expect(healthOf(rule(), ok, { events, hits: { Papier: false } })[0].code).toBe(
      "keyword_unused",
    );
  });
  it("matches keyword modes", () => {
    const r = rule({
      filter: {
        all_day: false,
        keywords: {
          columns: [],
          rows: [
            { match: "^Pa", mode: "regex" },
            { match: "Pap", mode: "startswith" },
          ],
        },
      },
    });
    expect(healthOf(r, ok, { events })).toEqual([]);
  });
  it("errors when the lookahead does not reach the earliest reminder", () => {
    const r = rule({ lookahead_days: 1 });
    expect(
      healthOf(r, ok, { events: [{ titles: ["Papier"], days_until: 0 }] }).map((i) => i.code),
    ).toEqual(["lookahead_short"]);
    expect(earliestOffsetDays(rule({ reminders: [{ at: "-2h" }, { at: "-3d 09:00" }] }))).toBe(3);
    expect(
      healthOf(rule({ lookahead_days: 2, reminders: [{ at: "-3h" }] }), ok, {
        events: [{ titles: ["Papier"], days_until: 0 }],
      }),
    ).toEqual([]);
  });
  it("informs about no enabled signal", () => {
    const items = healthOf(rule({ signals: [push({ enabled: false })] }), ok, { events });
    expect(items).toEqual([{ severity: "info", code: "no_signals", params: {} }]);
  });
  it("errors for push without recipients", () => {
    const r = rule({ signals: [push({ audience: undefined }), push({ audience: "all" })] });
    expect(healthOf(r, ok, { events })).toEqual([
      { severity: "error", code: "push_no_recipient", params: { n: "1" } },
    ]);
  });
  it("skips event checks for trigger rules and without preview", () => {
    const t = rule({ start_triggers: [{ trigger: "state", entity_id: "sensor.s" }] });
    expect(codes(healthOf(t, hass({ "sensor.s": "1" }), { events: [] }))).toEqual([]);
    expect(healthOf(rule(), ok)).toEqual([]);
  });
});

describe("panel health tab", () => {
  it("routes", () => {
    expect(PANEL_TABS).toContain("health");
    expect(parsePanelPath("/health").tab).toBe("health");
    expect(panelPath("health")).toBe("/health");
  });
});
