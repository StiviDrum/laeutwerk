/** Rule data as sent by the laeutwerk websocket API (see docs/SPEC.md). */

export type MatchMode = "contains" | "startswith" | "regex";
export type SignalType = "notify" | "light_signal" | "announce" | "action";
export type ReminderState = "planned" | "reminded" | "done" | "missed";
export type HaConfig = Record<string, unknown>;

export interface KeywordRow {
  match: string;
  mode?: MatchMode;
  /** Own colour of the keyword (#rrggbb). */
  color?: string;
  /** Own icon of the keyword (mdi:…). */
  icon?: string;
  [column: string]: string | undefined;
}

/** Icon and colour of one matching keyword row (either may be missing). */
export interface Badge {
  icon: string | null;
  color: string | null;
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
  /** Blink in the colours of the matching keywords. */
  color_from_keyword?: boolean;
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

export interface EarlySetting {
  mode: "off" | "hours" | "always";
  hours: number;
}

export interface Acknowledge {
  type: "notify_action" | "tag" | "trigger";
  tag_id?: string;
  name?: string;
  trigger?: HaConfig | HaConfig[];
}

export interface Reminder {
  id: string;
  rule_id: string;
  day: string;
  start: string;
  end: string;
  state: ReminderState;
  titles: string[];
  /** Headline rendered by the backend from the rule's headline template. */
  headline?: string | null;
  /** One badge per matching keyword row, in order. */
  badges?: Badge[];
  variables?: Record<string, string>;
  reminded_at: string | null;
  finished_at: string | null;
  acknowledged_by: string | null;
  acknowledged_via: string | null;
  snoozed_until: string | null;
  next_reminder_at?: string | null;
  assignee?: string | null;
  assignee_name?: string | null;
  /** Name of the person the substitute stands in for. */
  substitute_for_name?: string | null;
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
  headline?: string | null;
  badges?: Badge[];
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
  /** Headline template, e.g. "{wann}: {titel}" (empty = default). */
  headline?: string | null;
  headline_plural?: string | null;
  repeat: "none" | { every: number | string; max?: number };
  bundle: boolean;
  expire: string;
  /** Days of calendar to look ahead (1-365, default 14). */
  lookahead_days?: number;
  /** false = hidden in overview, upcoming, done and compact card. */
  visible?: boolean;
  interval?: { every: number | string; start?: string } | null;
  /** Source "trigger": the reminder starts when one of these fires. */
  start_triggers?: HaConfig[] | null;
  /** Short confirmation to the person who finished the task. */
  confirm?: { message: string; clear_after: number } | null;
  /** Finishing before the event: off, up to N hours before, or always. */
  early?: EarlySetting;
  /** Short message to the person who tried to finish too early. */
  early_feedback?: { message: string; clear_after: number } | null;
  activation?: {
    conditions: HaConfig[];
    match?: "all" | "any";
    season?: { from: string; to: string };
  } | null;
  on_done?: HaConfig[];
  assignee?: {
    persons: string[];
    rotation?: Rotation;
    substitute?: string;
    substitute_when?: { entity_id: string; state: string };
  } | null;
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
  /** Sample bundle (>= 2 titles) when no real one exists; may be missing on older backends. */
  plural_sample?: UpcomingEvent | null;
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
    notifyOnError?: boolean,
    returnResponse?: boolean,
  ): Promise<unknown>;
}
