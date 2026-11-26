/** The rule as one readable sentence; every named piece belongs to an editor group. */
import { describeTimespec, isTriggerRule } from "./format";
import type { Localizer, StringKey } from "./localize";
import type { Rule } from "./types";

export type SentenceKey =
  "src" | "kw" | "when" | "sig" | "rep" | "esc" | "exp" | "asg" | "act" | "ack";

export interface SentenceToken {
  text: string;
  /** Clickable piece: the editor group it opens (plain text when missing). */
  key?: SentenceKey;
}

/** Editor group (`data-step`) that holds the setting of a sentence piece. */
export const SENTENCE_STEP: Record<SentenceKey, number> = {
  src: 1,
  kw: 2,
  when: 3,
  rep: 3,
  sig: 4,
  ack: 5,
  exp: 6,
  esc: 7,
  asg: 7,
  act: 7,
};

function duration(value: number | string, defaultUnit: string, l: Localizer): string {
  const m = /^(\d+)\s*([mhdw])?$/.exec(String(value).trim());
  if (!m) return String(value);
  return `${m[1]} ${l.t(`sen_u_${m[2] ?? defaultUnit}` as StringKey)}`;
}

function list(parts: string[], l: Localizer): string {
  return parts.join(` ${l.t("sen_and")} `);
}

function triggerText(
  trigger: Record<string, unknown>,
  l: Localizer,
  names: (id: string) => string,
) {
  const id = typeof trigger.entity_id === "string" ? trigger.entity_id : "";
  const name = id ? names(id) : l.t("sen_an_entity");
  if (trigger.trigger === "state") {
    return trigger.to
      ? l.t("sen_trig_state", { name, to: String(trigger.to) })
      : l.t("sen_trig_change", { name });
  }
  if (trigger.trigger === "time") return l.t("sen_trig_time", { at: String(trigger.at ?? "") });
  return l.t("sen_trig_other");
}

/** Reminder time as a sentence part ("am Vortag um 17:00"); `bare` = plain clock time of an interval. */
function whenText(at: string, l: Localizer, bare: boolean): string {
  const v = at.trim().toLowerCase().replace(/\s+/g, " ");
  if (v === "event_end") return l.t("sen_at_end");
  if (v === "event_start") return l.t("sen_at_start");
  const wall = /^(?:(?:([+-]?\d{1,3})d|event_day) )?(\d{1,2}):(\d{2})$/.exec(v);
  if (wall) {
    const days = Number(wall[1] ?? 0);
    const time = `${wall[2].padStart(2, "0")}:${wall[3]}`;
    if (days === 0) return l.t(bare ? "sen_at_time" : "sen_at_same", { time });
    if (days === -1) return l.t("sen_at_before1", { time });
    return l.t(days < 0 ? "sen_at_before" : "sen_at_after", { n: Math.abs(days), time });
  }
  const off = /^-(\d{1,4}) ?([dhm])$/.exec(v);
  if (off) {
    const n = Number(off[1]);
    if (off[2] === "h") return l.t(n === 1 ? "sen_at_h1" : "sen_at_h", { n });
    if (off[2] === "m") return l.t("sen_at_m", { n });
    return l.t("sen_at_days", { n });
  }
  return describeTimespec(at, l);
}

export function ruleTokens(
  rule: Rule,
  l: Localizer,
  names: (entityId: string) => string = (id) => id,
): SentenceToken[] {
  const out: SentenceToken[] = [];
  const text = (t: string) => out.push({ text: t });
  const piece = (key: SentenceKey, t: string) => out.push({ text: t, key });
  const trigger = isTriggerRule(rule);
  const interval = !trigger && !!rule.interval && !rule.sources.length;
  const times = list(
    rule.reminders.map((r) => whenText(r.at, l, interval)),
    l,
  );
  if (trigger) {
    text(l.t("sen_tr_a"));
    const triggers = (rule.start_triggers ?? []) as Record<string, unknown>[];
    piece(
      "src",
      triggers.map((t) => triggerText(t, l, names)).join(` ${l.t("sen_or")} `) ||
        l.t("sen_a_trigger"),
    );
    text(l.t("sen_tr_b"));
    piece("when", l.t("sen_now"));
  } else if (interval && rule.interval) {
    text(l.t("sen_iv_a"));
    const start = rule.interval.start?.match(/^\d{4}-(\d{2})-(\d{2})/);
    piece(
      "src",
      duration(rule.interval.every, "d", l) +
        (start ? l.t("sen_iv_from", { date: `${Number(start[2])}.${Number(start[1])}.` }) : ""),
    );
    text(l.t("sen_iv_b"));
    piece("when", times || l.t("sen_never_at"));
  } else {
    text(l.t("sen_cal_a"));
    const cals = rule.sources.map((id) => `„${names(id)}“`);
    piece(
      "src",
      cals.length
        ? l.t(cals.length > 1 ? "sen_src_cals" : "sen_src_cal", { list: list(cals, l) })
        : l.t("sen_no_source"),
    );
    text(l.t("sen_cal_b"));
    const words = rule.filter.keywords.rows.map((r) => r.match).filter((m) => m.trim());
    piece(
      "kw",
      words.length
        ? l.t("sen_kw", { list: words.map((w) => `„${w.trim()}“`).join(", ") })
        : l.t("sen_kw_any"),
    );
    text(l.t("sen_cal_c"));
    piece("when", times || l.t("sen_never_at"));
  }
  const types = [...new Set(rule.signals.filter((s) => s.enabled).map((s) => s.type))];
  text(l.t("sen_sig_a"));
  piece("sig", types.map((t) => l.t(`type_${t}` as StringKey)).join(", ") || l.t("sen_no_signal"));
  text(`. ${l.t("sen_then")}`);
  const rep = rule.repeat;
  piece(
    "rep",
    rep === "none" || !rep
      ? l.t("sen_rep_none")
      : l.t(rep.max ? "sen_rep_max" : "sen_rep", {
          every: duration(rep.every, "m", l),
          max: rep.max ?? 0,
        }),
  );
  text(", ");
  const stages = rule.escalation ?? [];
  piece(
    "esc",
    stages.length
      ? l.t("sen_esc", {
          list: list(
            stages.map((s) =>
              /^\d{1,2}:\d{2}$/.test(String(s.after))
                ? l.t("sen_esc_at", { t: s.after })
                : l.t("sen_esc_after", { d: duration(s.after, "m", l) }),
            ),
            l,
          ),
        })
      : l.t("sen_esc_none"),
  );
  text(`. ${l.t("sen_exp_a")}`);
  const expire = rule.expire.trim();
  const day = /^event_day (\d{1,2}:\d{2})$/.exec(expire);
  piece(
    "exp",
    expire === "never"
      ? l.t("sen_exp_never")
      : l.t("sen_exp", {
          when:
            expire === "event_end"
              ? l.t("expire_event_end")
              : day
                ? `${l.t("expire_event_day")} ${day[1]}`
                : expire,
        }),
  );
  text(`. ${l.t("sen_asg_a")}`);
  const persons = rule.assignee?.persons ?? [];
  piece("asg", persons.length ? list(persons.map(names), l) : l.t("sen_asg_none"));
  text(`. ${l.t("sen_act_a")}`);
  const season = rule.activation?.season;
  const conditions = rule.activation?.conditions?.length ?? 0;
  const dm = (iso: string) => iso.split("-").reverse().join(".");
  piece(
    "act",
    (season
      ? l.t("sen_act_season", { from: dm(season.from), to: dm(season.to) })
      : l.t("sen_act_all")) + (conditions ? l.t("sen_act_cond", { n: conditions }) : ""),
  );
  text(`. ${l.t("sen_ack_a")}`);
  const ways = [l.t("sen_ack_card")];
  if (
    rule.signals.some(
      (s) => s.type === "notify" && (s.actions ?? []).some((a) => (a as { ack?: boolean }).ack),
    )
  )
    ways.push(l.t("sen_ack_push"));
  for (const a of rule.acknowledge) {
    if (a.type === "tag") ways.push(l.t("sen_ack_tag"));
    else if (a.type === "trigger") ways.push(l.t("sen_ack_sensor"));
  }
  piece("ack", [...new Set(ways)].join(", "));
  text(".");
  return out;
}

export const sentenceText = (tokens: SentenceToken[]): string => tokens.map((t) => t.text).join("");
