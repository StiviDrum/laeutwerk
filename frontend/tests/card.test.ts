import { describe, expect, it } from "vitest";
import { localizer } from "../src/localize";
import { applyRuleEvent } from "../src/rule-events";
import type { Rule } from "../src/types";

const r = (id: string, name = id) => ({ id, name }) as Rule;

describe("rule subscription events", () => {
  it("applies init, added, updated and removed", () => {
    let rules = applyRuleEvent(undefined, { event: "init", rules: [r("a"), r("b")] });
    expect(rules.map((x) => x.id)).toEqual(["a", "b"]);
    rules = applyRuleEvent(rules, { event: "added", rule_id: "c", rule: r("c") });
    rules = applyRuleEvent(rules, { event: "updated", rule_id: "a", rule: r("a", "A") });
    expect(rules.map((x) => x.name)).toEqual(["A", "b", "c"]);
    rules = applyRuleEvent(rules, { event: "removed", rule_id: "b", rule: null });
    expect(rules.map((x) => x.id)).toEqual(["a", "c"]);
    // updated without payload keeps the list
    expect(applyRuleEvent(rules, { event: "updated", rule_id: "a" })).toBe(rules);
  });
});

describe("localizer", () => {
  it("falls back to English and fills placeholders", () => {
    expect(localizer("de").t("n_open", { n: 2 })).toBe("2 offen");
    expect(localizer("fr").t("n_open", { n: 2 })).toBe("2 open");
    expect(localizer(undefined).weekdayShort(0)).toBe("Mon");
  });
});

describe("card editor", () => {
  it("drops empty values and keys of the other view", async () => {
    const { cleanCardConfig } = await import("../src/card-editor");
    expect(
      cleanCardConfig({
        type: "custom:laeutwerk-card",
        view: "overview",
        rule: "muell",
        rules: [],
        compact: false,
      }),
    ).toEqual({ type: "custom:laeutwerk-card", view: "overview", compact: false });
    expect(
      cleanCardConfig({ type: "", view: "rule", rule: "muell", rules: ["a"] } as never),
    ).toEqual({ type: "", view: "rule", rule: "muell" });
  });
});
