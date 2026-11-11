/** Rule data as sent by the laeutwerk websocket API (see docs/SPEC.md). */

export type MatchMode = "contains" | "startswith" | "regex";
export type SignalType = "notify" | "light_signal" | "announce" | "action";
export type ReminderState = "planned" | "reminded" | "done" | "missed";
export type HaConfig = Record<string, unknown>;

export interface KeywordRow {
  match: string;
  mode?: MatchMode;
  [column: string]: string | undefined;
}

export interface QuietTime {
  from: string;
  to: string;
  mode: "skip" | "defer";
}

export interface PushButton {
  label: string;
  ack?: boolean;
  snooze?: string | number;
}

export interface Signal {
  id?: string;
  type: SignalType;
  enabled: boolean;
  when: "now" | { opportunity: HaConfig | HaConfig[]; manual_only?: boolean };
  conditions?: HaConfig[];
  conditions_match?: "all" | "any";
  limit?: { per_reminder?: number; min_interval?: number };
  quiet?: QuietTime[];
  // notify
  targets?: string[];
  audience?: "all" | "present" | "persons" | "assignee";
  only_present?: boolean;
  stage?: number;
  persons?: string[];
  title?: string;
  title_plural?: string;
  message?: string;
  message_plural?: string;
  actions?: PushButton[] | HaConfig[];
  data?: HaConfig;
  // light_signal
  entities?: string[];
  pattern?: { effect?: "blink" | "pulse"; count?: number; interval?: number };
  color?: string;
  color_from?: string;
  brightness?: number;
  restore?: boolean;
  // announce
  players?: string[];
  text?: string;
  text_plural?: string;
  volume?: number;
  tts?: string;
  language?: string;
  voice?: string;
}

export interface Acknowledge {
  type: "notify_action" | "tag" | "trigger";
  tag_id?: string;
  name?: string;
  trigger?: HaConfig | HaConfig[];
  early?: boolean;
}

export interface Reminder {
  id: string;
  rule_id: string;
  day: string;
  start: string;
  end: string;
  state: ReminderState;
  titles: string[];
  colors?: string[];
  variables?: Record<string, string>;
  reminded_at: string | null;
  finished_at: string | null;
  acknowledged_by: string | null;
  acknowledged_via: string | null;
  snoozed_until: string | null;
  next_reminder_at?: string | null;
  assignee?: string | null;
  assignee_name?: string | null;
  stage?: number;
  signals_sent?: Record<string, number>;
  signal_last?: Record<string, string>;
  deferred?: Record<string, string>;
  /** Resolved NFC tag ids that acknowledge this reminder. */
  tags?: string[];
  expires_at?: string;
}

export interface HistoryEntry {
  reminder_id: string;
  day: string;
  titles: string[];
  state: "done" | "missed";
  reminded_at: string | null;
  finished_at: string | null;
  acknowledged_by: string | null;
  acknowledged_via: string | null;
  signals_sent: number;
}

export interface UpcomingEvent {
  id: string;
  day: string;
  start: string;
  end: string;
  titles: string[];
  days_until: number;
  colors: string[];
  all_day: boolean;
  variables: Record<string, string>;
  reminder_times?: string[];
  expires_at?: string;
  /** Resolved NFC tag ids ("{nfc}" per hit). */
  tags?: string[];
}

export interface RuleStatus {
  active?: boolean;
  assignee_stats?: Record<string, number>;
  state: ReminderState | "inactive";
  current: string | null;
  reminders: Reminder[];
  next_event: UpcomingEvent | null;
  errors: Record<string, string>;
}

export interface Rule {
  id?: string;
  name: string;
  icon: string | null;
  color: string | null;
  enabled: boolean;
  sources: string[];
  filter: { all_day: boolean; keywords: { columns: ColumnSpec[]; rows: KeywordRow[] } };
  reminders: { at: string }[];
  signals: Signal[];
  acknowledge: Acknowledge[];
  ack_label: string | null;
  repeat: "none" | { every: number | string; max?: number };
  bundle: boolean;
  expire: string;
  interval?: { every: number | string; start?: string } | null;
  activation?: {
    conditions: HaConfig[];
    match?: "all" | "any";
    season?: { from: string; to: string };
  } | null;
  on_done?: HaConfig[];
  assignee?: { persons: string[]; rotation?: Rotation } | null;
  escalation?: { after: string; color?: string }[];
  status?: RuleStatus;
}

/**
 * Keyword column: its name (plural variable "<name>n"), or an object with
 * `plural: false` (no plural variable) or an own plural name.
 */
export type ColumnSpec = string | { name: string; plural?: boolean | string };

export interface PersonInfo {
  entity_id: string;
  name: string;
  state: string;
  /** Notify actions of the person's phones with the companion app. */
  notify: string[];
}

export type Rotation = "fixed" | "weekly" | "per_event" | "after_last";

export interface RuleTemplate {
  id: string;
  name: string;
  description: string;
  builtin: boolean;
  rule: Partial<Rule>;
}

export interface RuleEvent {
  event: "init" | "added" | "updated" | "removed" | "reordered";
  rule_ids?: string[];
  rules?: Rule[];
  rule_id?: string;
  rule?: Rule | null;
}

export interface TitleSuggestion {
  title: string;
  count: number;
  matched: boolean;
}

export interface PreviewResult {
  titles?: TitleSuggestion[];
  events: UpcomingEvent[];
  total_events: number;
  errors: Record<string, string>;
  variables: string[];
}

export interface LaeutwerkCardConfig {
  type: string;
  view?: "overview" | "rule";
  rule?: string;
  rules?: string[];
  show_upcoming?: boolean;
  show_done?: boolean;
  compact?: boolean;
}

/** The subset of Home Assistant's `hass` object the card uses. */
export interface HassEntity {
  entity_id: string;
  state: string;
  attributes: Record<string, unknown>;
}

export interface HassConnection {
  subscribeMessage<T>(
    callback: (msg: T) => void,
    msg: Record<string, unknown>,
  ): Promise<() => Promise<void> | void>;
}

export interface HomeAssistant {
  states: Record<string, HassEntity>;
  locale?: { language: string };
  language?: string;
  config?: { time_zone?: string };
  themes?: { darkMode?: boolean };
  user?: { is_admin?: boolean; name?: string };
  connection: HassConnection;
  callWS<T>(msg: Record<string, unknown>): Promise<T>;
  callService(
    domain: string,
    service: string,
    data?: Record<string, unknown>,
    target?: Record<string, unknown>,
  ): Promise<unknown>;
}
