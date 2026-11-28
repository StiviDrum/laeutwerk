import { describe, expect, it } from "vitest";
import { healthOf } from "../src/health";
import {
  providerExamples,
  setProviders,
  unknownVariables,
  variableSuggestions,
} from "../src/providers";
import type { ProviderInfo } from "../src/providers";
import type { Rule } from "../src/types";

const providers: ProviderInfo[] = [
  {
    key: "rando",
    title: "Randowerk",
    variables: [{ name: "beleidigung", description: "Zufall", example: "Schussel" }],
  },
];

describe("provider variables", () => {
  it("lists built-ins first, then the provider group with hint", () => {
    const list = variableSuggestions(["titel", "wann"], "", providers, "de");
    expect(list.map((i) => i.value)).toEqual(["titel", "wann", "beleidigung"]);
    expect(list[2].group).toBe("Randowerk");
    expect(list[2].description).toBe("Zufall · z. B. Schussel");
    expect(variableSuggestions(["titel"], "bel", providers, "en").map((i) => i.value)).toEqual([
      "beleidigung",
    ]);
  });
  it("gives examples for previews", () => {
    expect(providerExamples(providers)).toEqual({ beleidigung: "Schussel" });
  });
  it("finds unknown variables", () => {
    expect(unknownVariables(["{titel} {beleidigung} {x}"], ["titel"], providers)).toEqual(["x"]);
  });
  it("health reports unknown variables in signal texts", () => {
    const rule = {
      filter: { all_day: false, keywords: { columns: [], rows: [] } },
      reminders: [],
      signals: [
        {
          type: "notify",
          enabled: true,
          when: "now",
          audience: "present",
          message: "{foo} {wann}",
        },
      ],
    } as unknown as Rule;
    const items = healthOf(rule, undefined);
    expect(items.find((i) => i.code === "unknown_variable")?.params.name).toBe("foo");
  });
  it("flags provider variables in the headline", () => {
    setProviders(providers);
    const rule = {
      headline: "{beleidigung}",
      filter: { all_day: false, keywords: { columns: [], rows: [] } },
      reminders: [],
      signals: [],
    } as unknown as Rule;
    expect(healthOf(rule, undefined).some((i) => i.code === "headline_provider_variable")).toBe(
      true,
    );
    setProviders([]);
  });
});
