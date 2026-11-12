import { describe, expect, it, vi } from "vitest";
import { ensureConfigTranslations } from "../src/ha-field";
import type { HomeAssistant } from "../src/types";

describe("ensureConfigTranslations", () => {
  it("ignores other selectors, loads config once for automation selectors", async () => {
    const load = vi.fn().mockResolvedValue(undefined);
    const hass = { loadFragmentTranslation: load } as unknown as HomeAssistant;
    expect(ensureConfigTranslations(hass, "entity")).toBeUndefined();
    expect(load).not.toHaveBeenCalled();
    await ensureConfigTranslations(hass, "trigger");
    await ensureConfigTranslations(hass, "action");
    expect(load).toHaveBeenCalledTimes(1);
    expect(load).toHaveBeenCalledWith("config");
  });
});
