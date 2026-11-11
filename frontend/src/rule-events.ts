import type { Rule, RuleEvent } from "./types";

/** Apply a `laeutwerk/rules/subscribe` event to the list of rules. */
export function applyRuleEvent(rules: Rule[] | undefined, msg: RuleEvent): Rule[] {
  if (msg.event === "init") return msg.rules ?? [];
  const list = rules ?? [];
  if (msg.event === "removed") return list.filter((r) => r.id !== msg.rule_id);
  if (!msg.rule) return list;
  const index = list.findIndex((r) => r.id === msg.rule_id);
  if (index < 0) return [...list, msg.rule];
  return list.map((r, i) => (i === index ? msg.rule! : r));
}
