/** Pure helpers of the panel: URL state and rule list filtering. */
import type { Rule } from "./types";

export type PanelTab = "overview" | "rules" | "health";
/** Tab ids in display order; later stages append (history, week, health). */
export const PANEL_TABS: PanelTab[] = ["overview", "rules", "health"];

export interface PanelRoute {
  tab: PanelTab;
  /** Selected rule id; "" = none, "new" is never used (new rules have no id). */
  ruleId: string;
}

/** Parse the part of the URL after the panel prefix ("/rules/muell"). */
export function parsePanelPath(path: string | undefined): PanelRoute {
  const parts = (path ?? "").split("/").filter(Boolean);
  if (parts[0] === "rules") {
    let id = parts[1] ?? "";
    try {
      id = decodeURIComponent(id);
    } catch {
      /* keep raw id */
    }
    return { tab: "rules", ruleId: id };
  }
  if (parts[0] === "health") return { tab: "health", ruleId: "" };
  return { tab: "overview", ruleId: "" };
}

export function panelPath(tab: PanelTab, ruleId = ""): string {
  if (tab === "rules") return ruleId ? `/rules/${encodeURIComponent(ruleId)}` : "/rules";
  if (tab === "health") return "/health";
  return "/overview";
}

/** Rules whose name or id contains the query (case-insensitive, trimmed). */
export function filterRules(rules: Rule[], query: string): Rule[] {
  const q = query.trim().toLowerCase();
  if (!q) return rules;
  return rules.filter((r) => `${r.name} ${r.id ?? ""}`.toLowerCase().includes(q));
}

/** Narrow layout: HA says so or the panel is at most 870 px wide. */
export function isNarrow(narrow: boolean | undefined, width: number): boolean {
  return !!narrow || (width > 0 && width <= 870);
}
