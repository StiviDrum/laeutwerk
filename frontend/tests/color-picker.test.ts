import { describe, expect, it } from "vitest";
import { hexToHs, hsToHex, hsToXy, normalizeHex, xyToHs } from "../src/color-picker";

describe("color picker helpers", () => {
  it("normalises hex", () => {
    expect(normalizeHex("#ABC")).toBe("#aabbcc");
    expect(normalizeHex("abc")).toBe("#aabbcc");
    expect(normalizeHex(" #FF9500 ")).toBe("#ff9500");
    expect(normalizeHex("#12")).toBeNull();
    expect(normalizeHex("#gggggg")).toBeNull();
    expect(normalizeHex("")).toBeNull();
  });

  it("round-trips saturated colours", () => {
    for (const hex of [
      "#ff0000",
      "#ffff00",
      "#00ff00",
      "#00ffff",
      "#0000ff",
      "#ff00ff",
      "#ff9500",
    ]) {
      const { h, s } = hexToHs(hex);
      expect(hsToHex(h, s)).toBe(hex);
    }
  });

  it("gives hue and saturation for greys and dark colours", () => {
    expect(hexToHs("#ffffff")).toEqual({ h: 0, s: 0 });
    expect(hexToHs("#000000").s).toBe(0);
    const g = hexToHs("#8a8a94");
    expect(g.s).toBeGreaterThan(0);
    expect(g.s).toBeLessThan(0.3);
  });

  it("maps wheel positions", () => {
    expect(hsToHex(0, 0)).toBe("#ffffff");
    expect(xyToHs(0, 0).s).toBe(0);
    expect(xyToHs(1, 0)).toEqual({ h: 0, s: 1 });
    const down = xyToHs(0, 1);
    expect(down.h).toBeCloseTo(90);
    expect(down.s).toBeCloseTo(1);
    const p = hsToXy(120, 0.5);
    const back = xyToHs(p.x, p.y);
    expect(back.h).toBeCloseTo(120);
    expect(back.s).toBeCloseTo(0.5);
  });

  it("clamps points outside the circle", () => {
    expect(xyToHs(3, 0).s).toBe(1);
    expect(xyToHs(-2, -2).s).toBe(1);
  });
});
