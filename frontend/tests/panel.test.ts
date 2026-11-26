import { describe, expect, it } from "vitest";
import { filterRules, isNarrow, panelPath, parsePanelPath } from "../src/panel-logic";
import type { Rule } from "../src/types";

const r = (id: string, name: string) => ({ id, name }) as Rule;

describe("panel route", () => {
  it("parses tab and rule id", () => {
    expect(parsePanelPath("")).toEqual({ tab: "overview", ruleId: "" });
    expect(parsePanelPath(undefined).tab).toBe("overview");
    expect(parsePanelPath("/rules")).toEqual({ tab: "rules", ruleId: "" });
    expect(parsePanelPath("/rules/muell")).toEqual({ tab: "rules", ruleId: "muell" });
    expect(parsePanelPath("/rules/a%20b/")).toEqual({ tab: "rules", ruleId: "a b" });
    expect(parsePanelPath("/bogus").tab).toBe("overview");
  });
  it("round-trips paths", () => {
    expect(panelPath("rules", "a b")).toBe("/rules/a%20b");
    expect(parsePanelPath(panelPath("rules", "a b")).ruleId).toBe("a b");
    expect(panelPath("rules")).toBe("/rules");
    expect(panelPath("overview")).toBe("/overview");
    expect(parsePanelPath("/history").tab).toBe("history");
    expect(panelPath("history")).toBe("/history");
  });
});

describe("panel list", () => {
  const rules = [r("muell", "Müll rausstellen"), r("dienst", "Kult61-Dienst")];
  it("filters by name or id, case-insensitive", () => {
    expect(filterRules(rules, "")).toBe(rules);
    expect(filterRules(rules, " MÜLL ").map((x) => x.id)).toEqual(["muell"]);
    expect(filterRules(rules, "dienst").map((x) => x.id)).toEqual(["dienst"]);
    expect(filterRules(rules, "zzz")).toEqual([]);
  });
  it("detects narrow layout", () => {
    expect(isNarrow(true, 1200)).toBe(true);
    expect(isNarrow(false, 870)).toBe(true);
    expect(isNarrow(false, 871)).toBe(false);
    expect(isNarrow(false, 0)).toBe(false);
  });
});
