import { css } from "lit";

/** Design tokens (DESIGN.md C4): HA theme variables first, mockup values as fallback. */
export const tokens = css`
  :host {
    --lw-bg: var(--ha-card-background, var(--card-background-color, #151518));
    --lw-text: var(--primary-text-color, #f5f5f7);
    --lw-text-2: var(--secondary-text-color, rgba(245, 245, 247, 0.62));
    --lw-surface: color-mix(in srgb, var(--lw-text) 7%, transparent);
    --lw-surface-2: color-mix(in srgb, var(--lw-text) 11%, transparent);
    --lw-border: var(--ha-card-border-color, var(--divider-color, rgba(255, 255, 255, 0.1)));
    --lw-accent: var(--primary-color, #03a9f4);
    --lw-on-accent: var(--text-primary-color, #ffffff);
    --lw-ok: var(--success-color, #4ad295);
    --lw-danger: var(--error-color, #ff5a6e);
    --lw-radius-card: var(--ha-card-border-radius, 26px);
    font-family: var(--ha-font-family-body, inherit);
    color: var(--lw-text);
  }
  /* Dark themes: monochrome accent like the mockup / Bubble Card. */
  :host([dark]) {
    --lw-accent: var(--primary-text-color, #f5f5f7);
    --lw-on-accent: var(--primary-background-color, #0b0b0d);
  }
  button {
    font-family: inherit;
    color: inherit;
    cursor: pointer;
    border: 0;
    background: none;
    padding: 0;
  }
  button:disabled {
    opacity: 0.45;
    cursor: default;
  }
  button:focus-visible,
  input:focus-visible,
  select:focus-visible,
  textarea:focus-visible {
    outline: 2px solid var(--lw-accent);
    outline-offset: 2px;
  }
  ha-icon {
    --mdc-icon-size: 20px;
    display: inline-flex;
  }
`;

/** Shared pieces of the card and its editor pages. */
export const shared = css`
  /* Block heading + divider between independent features of one step. */
  .sublabel.head {
    font-size: 14px;
    color: var(--lw-text);
  }
  .sep {
    border: 0;
    border-top: 1px solid var(--lw-border);
    margin: 8px 0 4px;
  }
  .separator {
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 24px;
    margin-top: 6px;
    font-size: 15px;
    font-weight: 600;
  }
  .separator .line {
    flex: 1;
    height: 1px;
    background: var(--lw-border);
  }
  .list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  /* Lists with a thin line between the entries. */
  .divided {
    display: flex;
    flex-direction: column;
    gap: 0;
  }
  .divided > * {
    padding-top: 6px;
    padding-bottom: 6px;
  }
  .divided > * + * {
    border-top: 1px solid var(--lw-border);
  }
  .row {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }
  .grow {
    flex: 1;
    min-width: 0;
  }
  .wrap {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
  }
  .icon {
    width: 44px;
    height: 44px;
    border-radius: 22px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--lw-surface-2);
  }
  .icon.small {
    width: 36px;
    height: 36px;
    border-radius: 18px;
  }
  .icon ha-icon {
    --mdc-icon-size: 22px;
  }
  .name {
    font-size: 15px;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .sub {
    font-size: 13px;
    color: var(--lw-text-2);
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .hint {
    font-size: 12px;
    color: var(--lw-text-2);
    line-height: 1.4;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 28px;
    padding: 0 10px;
    border-radius: 14px;
    background: var(--lw-surface);
    font-size: 12px;
    font-weight: 500;
    white-space: nowrap;
  }
  button.chip {
    min-height: 36px;
    border-radius: 18px;
    padding: 0 12px;
  }
  .chip.accent {
    background: color-mix(in srgb, var(--lw-accent) 16%, transparent);
  }
  .chip.dashed {
    background: none;
    border: 1px dashed var(--lw-border);
    color: var(--lw-text-2);
  }
  .chip ha-icon {
    --mdc-icon-size: 14px;
  }
  .pill {
    min-height: 48px;
    padding: 0 18px;
    border-radius: 24px;
    font-size: 14px;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    box-sizing: border-box;
  }
  .pill.outline {
    border: 1px solid var(--lw-border);
  }
  .pill.primary {
    background: var(--lw-accent);
    color: var(--lw-on-accent);
    font-weight: 700;
  }
  .pill.danger {
    border: 1px solid color-mix(in srgb, var(--lw-danger) 55%, transparent);
    color: var(--lw-danger);
  }
  .actions {
    display: flex;
    gap: 10px;
  }
  .actions > * {
    flex: 1;
    min-width: 0;
  }
  .actions > .primary {
    flex: 2;
  }
  .segmented {
    display: flex;
    gap: 4px;
    padding: 3px;
    border-radius: 22px;
    background: var(--lw-surface);
  }
  .segmented button {
    flex: 1;
    min-height: 38px;
    border-radius: 19px;
    font-size: 13px;
    font-weight: 600;
    color: var(--lw-text-2);
    padding: 0 8px;
  }
  .segmented button[aria-pressed="true"] {
    background: var(--lw-accent);
    color: var(--lw-on-accent);
  }
  .switch {
    position: relative;
    width: 52px;
    height: 32px;
    flex-shrink: 0;
    border-radius: 16px;
    background: var(--lw-surface-2);
    padding: 3px;
    display: flex;
    justify-content: flex-start;
    box-sizing: border-box;
  }
  .switch::before {
    content: "";
    position: absolute;
    inset: -6px;
  }
  .switch span {
    width: 26px;
    height: 26px;
    border-radius: 13px;
    background: var(--lw-text-2);
    display: block;
  }
  .switch[aria-checked="true"] {
    background: var(--lw-accent);
    justify-content: flex-end;
  }
  .switch[aria-checked="true"] span {
    background: var(--lw-on-accent);
  }
  .panel {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 14px;
    border-radius: 20px;
    background: var(--lw-surface);
    border: 1px solid var(--lw-border);
  }
  .step {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 15px;
    font-weight: 600;
  }
  .step .num {
    width: 24px;
    height: 24px;
    border-radius: 12px;
    background: var(--lw-surface-2);
    font-size: 12px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  label.field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
    color: var(--lw-text-2);
    min-width: 0;
  }
  input,
  select,
  textarea {
    font: inherit;
    font-size: 14px;
    color: var(--lw-text);
    background: var(--lw-surface);
    border: 1px solid var(--lw-border);
    border-radius: 12px;
    padding: 0 12px;
    min-height: 44px;
    box-sizing: border-box;
    min-width: 0;
    width: 100%;
  }
  textarea {
    padding: 10px 12px;
    min-height: 72px;
    resize: vertical;
  }
  select option {
    color: #111;
    background: #fff;
  }
  input[type="number"] {
    width: 84px;
  }
  input[type="time"] {
    width: 128px;
    padding: 0 8px;
  }
  .toggle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    min-height: 44px;
    font-size: 14px;
  }
  .pill.wide {
    width: 100%;
  }
  .error {
    font-size: 13px;
    padding: 10px 12px;
    border-radius: 12px;
    background: color-mix(in srgb, var(--lw-danger) 14%, transparent);
    color: var(--lw-danger);
  }
  .mini {
    width: 36px;
    height: 36px;
    flex-shrink: 0;
    border-radius: 18px;
    background: var(--lw-surface-2);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    position: relative;
  }
  .mini::before {
    content: "";
    position: absolute;
    inset: -4px;
  }
  .mini ha-icon {
    --mdc-icon-size: 18px;
  }
`;
