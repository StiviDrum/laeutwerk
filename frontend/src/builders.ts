/** Pure parse/format helpers behind the form builders (no shortcode typing in the UI).
 *  Every parser returns null for values it cannot represent exactly; callers then
 *  leave the stored value untouched. parse -> format is always the identity. */

export type DurationUnit = "m" | "h" | "d" | "w";
export interface DurationParts {
  amount: number;
  unit: DurationUnit;
  /** Stored without a unit (plain minutes / plain days). */
  bare?: boolean;
}

const UNIT_MINUTES: Record<DurationUnit, number> = { m: 1, h: 60, d: 1440, w: 10080 };

/** "30m" / "3h" / "1d" / "2w" / "90" (bare = minutes). */
export function parseDuration(
  value: string | number | undefined,
  units: DurationUnit[] = ["m", "h", "d"],
): DurationParts | null {
  const text = String(value ?? "");
  const m = /^(\d{1,5})([mhdw]?)$/.exec(text);
  if (!m || Number(m[1]) < 1) return null;
  const unit = (m[2] || "m") as DurationUnit;
  if (!units.includes(unit)) return null;
  return { amount: Number(m[1]), unit, bare: !m[2] || undefined };
}

export function formatDuration(p: DurationParts): string {
  return p.bare ? String(p.amount) : `${p.amount}${p.unit}`;
}

/** Minutes <-> amount + unit for numeric minute fields (repeat interval). */
export function minutesToParts(minutes: number, units: DurationUnit[] = ["m", "h"]): DurationParts {
  for (const unit of [...units].reverse()) {
    if (minutes % UNIT_MINUTES[unit] === 0) return { amount: minutes / UNIT_MINUTES[unit], unit };
  }
  return { amount: minutes, unit: "m" };
}

export function partsToMinutes(p: DurationParts): number {
  return p.amount * UNIT_MINUTES[p.unit];
}

export interface IntervalParts {
  amount: number;
  unit: "d" | "w";
  /** Stored as a plain number of days. */
  number?: boolean;
}

/** Interval every: 90 / "90d" / "12w". */
export function parseInterval(value: number | string | undefined): IntervalParts | null {
  if (typeof value === "number") {
    return Number.isInteger(value) && value >= 1
      ? { amount: value, unit: "d", number: true }
      : null;
  }
  const m = /^(\d{1,4})([dw])$/.exec(value ?? "");
  return m && Number(m[1]) >= 1 ? { amount: Number(m[1]), unit: m[2] as "d" | "w" } : null;
}

export function formatInterval(p: IntervalParts): number | string {
  return p.number ? p.amount : `${p.amount}${p.unit}`;
}

export type TimeParts =
  | { kind: "wall"; days: number; clock: string; named?: boolean }
  | { kind: "offset"; amount: number; unit: "m" | "h" | "d" }
  | { kind: "start" }
  | { kind: "end" };

const CLOCK = "([01]\\d|2[0-3]):[0-5]\\d";

/** "-1d 17:00", "09:00", "event_day 10:00", "-2h", "+12h", "event_start", "event_end". */
export function parseTimespec(text: string): TimeParts | null {
  let m: RegExpExecArray | null;
  if (text === "event_start") return { kind: "start" };
  if (text === "event_end") return { kind: "end" };
  if ((m = new RegExp(`^event_day (${CLOCK})$`).exec(text)))
    return { kind: "wall", days: 0, clock: m[1], named: true };
  if ((m = new RegExp(`^(${CLOCK})$`).exec(text))) return { kind: "wall", days: 0, clock: m[1] };
  if ((m = new RegExp(`^([+-])([1-9]\\d{0,2})d (${CLOCK})$`).exec(text)))
    return { kind: "wall", days: (m[1] === "-" ? -1 : 1) * Number(m[2]), clock: m[3] };
  if ((m = /^([+-])([1-9]\d{0,3})([dhm])$/.exec(text)))
    return {
      kind: "offset",
      amount: (m[1] === "-" ? -1 : 1) * Number(m[2]),
      unit: m[3] as "m" | "h" | "d",
    };
  return null;
}

export function formatTimespec(p: TimeParts): string {
  switch (p.kind) {
    case "start":
      return "event_start";
    case "end":
      return "event_end";
    case "offset":
      return `${p.amount < 0 ? "-" : "+"}${Math.abs(p.amount)}${p.unit}`;
    default:
      if (p.named) return `event_day ${p.clock}`;
      if (p.days === 0) return p.clock;
      return `${p.days < 0 ? "-" : "+"}${Math.abs(p.days)}d ${p.clock}`;
  }
}

export type SpecKind =
  "wall_before" | "same" | "wall_after" | "off_before" | "off_after" | "start" | "end";

export const SPEC_KINDS: SpecKind[] = [
  "wall_before",
  "same",
  "wall_after",
  "off_before",
  "off_after",
  "start",
  "end",
];

export function specKindOf(p: TimeParts): SpecKind {
  if (p.kind === "wall") return p.days < 0 ? "wall_before" : p.days > 0 ? "wall_after" : "same";
  if (p.kind === "offset") return p.amount < 0 ? "off_before" : "off_after";
  return p.kind;
}

/** Parts for a freshly chosen kind, keeping amount/clock of the previous parts. */
export function specPartsFor(kind: SpecKind, prev: TimeParts | null): TimeParts {
  const clock = prev?.kind === "wall" ? prev.clock : "17:00";
  const days = prev?.kind === "wall" ? Math.abs(prev.days) || 1 : 1;
  const off = prev?.kind === "offset" ? prev : { amount: 2, unit: "h" as const };
  const n = Math.abs(off.amount);
  switch (kind) {
    case "wall_before":
      return { kind: "wall", days: -days, clock };
    case "wall_after":
      return { kind: "wall", days, clock };
    case "same":
      return { kind: "wall", days: 0, clock };
    case "off_before":
      return { kind: "offset", amount: -n, unit: off.unit };
    case "off_after":
      return { kind: "offset", amount: n, unit: off.unit };
    default:
      return { kind };
  }
}
