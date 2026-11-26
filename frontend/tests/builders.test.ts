import { describe, expect, it } from "vitest";
import {
  formatDuration,
  formatInterval,
  formatTimespec,
  minutesToParts,
  parseDuration,
  parseInterval,
  parseTimespec,
  partsToMinutes,
  specKindOf,
  specPartsFor,
} from "../src/builders";

describe("builders round trip", () => {
  it.each([
    "-1d 17:00",
    "09:00",
    "-2h",
    "-30m",
    "-7d",
    "+12h",
    "+1d 12:00",
    "event_day 10:00",
    "event_start",
    "event_end",
  ])("timespec %s", (text) => {
    const parts = parseTimespec(text);
    expect(parts).not.toBeNull();
    expect(formatTimespec(parts!)).toBe(text);
  });

  it("leaves unrepresentable timespecs alone", () => {
    expect(parseTimespec("tomorrow")).toBeNull();
    expect(parseTimespec("-1d 25:00")).toBeNull();
    expect(parseTimespec("")).toBeNull();
  });

  it.each(["8h", "30m", "3h", "1d", "90", "2w"])("duration %s", (text) => {
    expect(formatDuration(parseDuration(text, ["m", "h", "d", "w"])!)).toBe(text);
  });

  it("duration respects the allowed units", () => {
    expect(parseDuration("2w")).toBeNull();
    expect(parseDuration("0h")).toBeNull();
    expect(parseDuration("x")).toBeNull();
  });

  it.each([90, "90d", "12w"])("interval %s", (v) => {
    expect(formatInterval(parseInterval(v)!)).toBe(v);
  });

  it.each([1, 45, 60, 120, 1440])("repeat minutes %i", (min) => {
    expect(partsToMinutes(minutesToParts(min))).toBe(min);
  });

  it("switches kind keeping amount and clock", () => {
    const before = parseTimespec("-2d 18:30")!;
    expect(specKindOf(before)).toBe("wall_before");
    expect(formatTimespec(specPartsFor("wall_after", before))).toBe("+2d 18:30");
    expect(formatTimespec(specPartsFor("same", before))).toBe("18:30");
    expect(formatTimespec(specPartsFor("off_after", parseTimespec("-3h")))).toBe("+3h");
  });
});
