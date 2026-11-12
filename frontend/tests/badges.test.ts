import { describe, expect, it } from "vitest";
import {
  DEFAULT_ICON,
  badgeLook,
  badgeLooks,
  filterSuggestions,
  singularHeadlinePreview,
  insertVariable,
  reminderTitle,
  variableQuery,
} from "../src/format";

const rule = { icon: "mdi:trash-can", color: "#2f6bff" };

describe("badge fallback", () => {
  it("falls back for icon and colour independently", () => {
    expect(badgeLook(rule, { icon: "mdi:leaf", color: "#00ff00" })).toEqual({
      icon: "mdi:leaf",
      color: "#00ff00",
    });
    // only icon -> rule colour
    expect(badgeLook(rule, { icon: "mdi:leaf", color: null })).toEqual({
      icon: "mdi:leaf",
      color: "#2f6bff",
    });
    // only colour -> rule icon in that colour
    expect(badgeLook(rule, { icon: null, color: "#ff0000" })).toEqual({
      icon: "mdi:trash-can",
      color: "#ff0000",
    });
  });

  it("uses the defaults without rule values or badge", () => {
    expect(badgeLook({ icon: null, color: null }, undefined)).toEqual({
      icon: DEFAULT_ICON,
      color: null,
    });
    expect(badgeLook(undefined, {})).toEqual({ icon: DEFAULT_ICON, color: null });
  });

  it("lists distinct looks of a bundle and never throws on missing data", () => {
    const looks = badgeLooks(rule, {
      badges: [
        { icon: "mdi:leaf", color: null },
        { icon: "mdi:leaf", color: null },
        { icon: null, color: "#ff0000" },
      ],
    });
    expect(looks).toEqual([
      { icon: "mdi:leaf", color: "#2f6bff" },
      { icon: "mdi:trash-can", color: "#ff0000" },
    ]);
    expect(badgeLooks(rule, undefined)).toEqual([{ icon: "mdi:trash-can", color: "#2f6bff" }]);
    expect(badgeLooks(rule, { badges: [] })).toHaveLength(1);
  });
});

describe("headline", () => {
  const base = { titles: ["Papier", "Bio"], variables: { wann: "morgen" } };
  it("prefers the rendered headline, else the default title", () => {
    expect(reminderTitle({ ...base, headline: "Tonnen raus!" })).toBe("Tonnen raus!");
    expect(reminderTitle({ ...base, headline: "  " })).toBe("Morgen: Papier + Bio");
    expect(reminderTitle({ ...base, headline: null })).toBe("Morgen: Papier + Bio");
    expect(reminderTitle(base)).toBe("Morgen: Papier + Bio");
  });
});

describe("variable autocomplete", () => {
  it("detects an open {query at the cursor", () => {
    expect(variableQuery("Stell {to", 9)).toEqual({ start: 6, query: "to" });
    expect(variableQuery("Stell {", 7)).toEqual({ start: 6, query: "" });
    expect(variableQuery("Stell {tonne} raus", 18)).toBeNull();
    expect(variableQuery("plain", 5)).toBeNull();
    // cursor before the brace
    expect(variableQuery("a {x", 1)).toBeNull();
  });

  it("filters case-insensitively, prefix matches first", () => {
    const items = ["tonne", "tonnen", "titel", "rest", "wann"].map((value) => ({ value }));
    expect(filterSuggestions(items, "t").map((i) => i.value)).toEqual([
      "tonne",
      "tonnen",
      "titel",
      "rest",
    ]);
    expect(filterSuggestions(items, "ON").map((i) => i.value)).toEqual(["tonne", "tonnen"]);
    expect(filterSuggestions(items, "zzz")).toEqual([]);
    expect(filterSuggestions(items, "", 2)).toHaveLength(2);
    expect(
      filterSuggestions([{ value: "abc123", label: "Mülltonne" }], "tonne").map((i) => i.value),
    ).toEqual(["abc123"]);
  });

  it("inserts the variable at the cursor and keeps the rest", () => {
    expect(insertVariable("Stell {to raus", 9, "tonne")).toEqual({
      text: "Stell {tonne} raus",
      cursor: 13,
    });
    // text after the cursor is untouched, a closing brace is not doubled
    expect(insertVariable("a {t} b", 4, "titel")).toEqual({ text: "a {titel} b", cursor: 9 });
    expect(insertVariable("no brace", 4, "x")).toBeNull();
  });
});

describe("headline field previews", () => {
  const single = { titles: ["Papier"], variables: { titel: "Papier", wann: "Morgen" } };
  const bundle = {
    titles: ["Papier", "Bio"],
    variables: { titel: "Papier und Bio", wann: "Morgen" },
  };
  const rule = { headline: "{wann}: {titel}" };

  it("singular uses the first single-match event, else the first", () => {
    expect(singularHeadlinePreview(rule, [bundle, single])).toBe("Morgen: Papier");
    expect(singularHeadlinePreview(rule, [bundle])).toBe("Morgen: Papier und Bio");
    expect(singularHeadlinePreview(rule, [])).toBe("");
  });
});
