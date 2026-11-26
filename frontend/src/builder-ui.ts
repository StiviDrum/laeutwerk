/** Stateless render helpers for the form builders (value in, value out). */
import { html, nothing, type TemplateResult } from "lit";
import {
  SPEC_KINDS,
  formatTimespec,
  parseDuration,
  parseTimespec,
  specKindOf,
  specPartsFor,
  type DurationUnit,
  type SpecKind,
} from "./builders";
import type { Localizer, StringKey } from "./localize";

const UNIT_KEY: Record<DurationUnit, StringKey> = {
  m: "u_m",
  h: "u_h",
  d: "u_d",
  w: "u_w",
};

const num = (e: Event): number =>
  Math.max(1, Math.round(Number((e.target as HTMLInputElement).value)) || 1);

export function expertOnly(l: Localizer): TemplateResult {
  return html`<div class="hint">${l.t("expert_only")}</div>`;
}

/** Number + unit select writing "3h" style durations; empty value = not set. */
export function durationField(
  l: Localizer,
  value: string | number | undefined,
  onChange: (value: string) => void,
  units: DurationUnit[] = ["m", "h", "d"],
  fallback: DurationUnit = "h",
): TemplateResult {
  const text = value === undefined || value === "" ? "" : String(value);
  const parts = text ? parseDuration(text, units) : null;
  if (text && !parts) return expertOnly(l);
  const amount = parts?.amount ?? "";
  const unit = parts && !parts.bare ? parts.unit : parts ? "m" : fallback;
  return html`<span class="row dur">
    <input
      type="number"
      min="1"
      .value=${String(amount)}
      @change=${(e: Event) => onChange(`${num(e)}${unit}`)}
    />
    <select
      @change=${(e: Event) =>
        onChange(`${parts?.amount ?? 1}${(e.target as HTMLSelectElement).value}`)}
    >
      ${units.map(
        (u) => html`<option value=${u} ?selected=${u === unit}>${l.t(UNIT_KEY[u])}</option>`,
      )}
    </select>
  </span>`;
}

/** Builder for reminder / expiry time specs ("-1d 17:00", "-2h", "event_end" ...). */
export function timespecField(
  l: Localizer,
  value: string,
  onChange: (value: string) => void,
): TemplateResult {
  const parts = parseTimespec(value);
  if (!parts) return expertOnly(l);
  const kind = specKindOf(parts);
  const set = (next: typeof parts) => onChange(formatTimespec(next));
  return html`<span class="row dur">
    <select
      @change=${(e: Event) =>
        set(specPartsFor((e.target as HTMLSelectElement).value as SpecKind, parts))}
    >
      ${SPEC_KINDS.map(
        (k) =>
          html`<option value=${k} ?selected=${k === kind}>${l.t(`tk_${k}` as StringKey)}</option>`,
      )}
    </select>
    ${
      parts.kind === "wall" && parts.days !== 0
        ? html`<input
            type="number"
            min="1"
            .value=${String(Math.abs(parts.days))}
            @change=${(e: Event) => set({ ...parts, days: Math.sign(parts.days) * num(e) })}
          />`
        : nothing
    }
    ${
      parts.kind === "wall"
        ? html`<input
            type="time"
            .value=${parts.clock}
            @change=${(e: Event) => {
              const clock = (e.target as HTMLInputElement).value;
              if (clock) set({ ...parts, clock });
            }}
          />`
        : nothing
    }
    ${
      parts.kind === "offset"
        ? html`<input
              type="number"
              min="1"
              .value=${String(Math.abs(parts.amount))}
              @change=${(e: Event) => set({ ...parts, amount: Math.sign(parts.amount) * num(e) })}
            />
            <select
              @change=${(e: Event) =>
                set({ ...parts, unit: (e.target as HTMLSelectElement).value as "m" | "h" | "d" })}
            >
              ${(["m", "h", "d"] as const).map(
                (u) =>
                  html`<option value=${u} ?selected=${u === parts.unit}>
                    ${l.t(UNIT_KEY[u])}
                  </option>`,
              )}
            </select>`
        : nothing
    }
  </span>`;
}
