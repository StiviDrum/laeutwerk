import { css, html, type TemplateResult } from "lit";
import { badgeLook, badgeLooks } from "./format";
import type { Badge, Rule } from "./types";

/**
 * Round icon of a rule. With a reminder/event the first keyword badge
 * (icon + colour, each falling back to the rule) fills the circle; more
 * distinct badges of a bundle are small overlapping circles (max. 2).
 */
export function badgeIcon(rule: Rule, small = false, item?: { badges?: Badge[] }): TemplateResult {
  const looks = item ? badgeLooks(rule, item) : [badgeLook(rule, undefined)];
  const circle = (look: { icon: string; color: string | null }, extra = false) => {
    const color = look.color ?? "var(--lw-text-2)";
    return html`<span
      class="icon ${small ? "small" : ""} ${extra ? "extra" : ""}"
      style="background: color-mix(in srgb, ${color} 22%, transparent); color: ${color}"
    >
      <ha-icon .icon=${look.icon}></ha-icon>
    </span>`;
  };
  if (looks.length < 2) return circle(looks[0]);
  return html`<span class="iconstack ${small ? "small" : ""}">
    ${circle(looks[0])}
    ${looks.slice(1, 3).map((look, i) => html`<span class="x${i}">${circle(look, true)}</span>`)}
  </span>`;
}

export const badgeIconStyles = css`
  .iconstack {
    position: relative;
    display: inline-flex;
    flex-shrink: 0;
  }
  .iconstack .x0,
  .iconstack .x1 {
    position: absolute;
    bottom: -4px;
    display: flex;
  }
  .iconstack .x0 {
    right: -6px;
  }
  .iconstack .x1 {
    right: 14px;
  }
  .iconstack .icon.extra {
    width: 22px;
    height: 22px;
    border-radius: 11px;
    box-shadow: 0 0 0 2px var(--lw-surface);
  }
  .iconstack .icon.extra ha-icon {
    --mdc-icon-size: 14px;
  }
`;
