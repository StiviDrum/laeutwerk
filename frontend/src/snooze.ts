/** Pure helpers of the "remind me later" menu. */
import type { StringKey } from "./localize";
import type { HomeAssistant } from "./types";

export type SnoozeData = { duration: string } | { until: string } | { until_home: string };

export interface SnoozeChoice {
  id: string;
  key: StringKey;
  data: SnoozeData;
}

/** Hour of day (0-23.99) of `now` in the given time zone. */
function localHour(now: Date, timeZone?: string): number {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const num = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? 0);
  return num("hour") + num("minute") / 60;
}

/** Entity id of the person whose `user_id` is the logged-in user. */
export function currentPerson(hass: HomeAssistant | undefined): string | undefined {
  const uid = hass?.user?.id;
  if (!uid) return undefined;
  return Object.entries(hass?.states ?? {}).find(
    ([id, s]) => id.startsWith("person.") && s.attributes?.user_id === uid,
  )?.[0];
}

/** Presets of the menu: 10/30 min, 1/3 h, tonight (before 18:00), tomorrow morning, until home. */
export function snoozeChoices(now: Date, timeZone?: string, person?: string): SnoozeChoice[] {
  const list: SnoozeChoice[] = [
    { id: "10m", key: "later_10m", data: { duration: "10m" } },
    { id: "30m", key: "later_30m", data: { duration: "30m" } },
    { id: "1h", key: "later_1h", data: { duration: "1h" } },
    { id: "3h", key: "later_3h", data: { duration: "3h" } },
  ];
  if (localHour(now, timeZone) < 18) {
    list.push({ id: "evening", key: "later_evening", data: { until: "18:00" } });
  }
  list.push({ id: "morning", key: "later_morning", data: { until: "07:00" } });
  if (person) list.push({ id: "home", key: "later_home", data: { until_home: person } });
  return list;
}
