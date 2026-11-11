// Mocked Home Assistant for dev/preview.html: the reference rules (SPEC B8),
// a fake websocket subscription and the services the card calls.
const params = new URLSearchParams(location.search);
if (params.get("theme") === "light") document.documentElement.classList.add("light");
const page = params.get("page") ?? "overview";

// Minimal stand-ins for HA's own elements.
customElements.define("ha-card", class extends HTMLElement {});
customElements.define(
  "ha-icon",
  class extends HTMLElement {
    set icon(v) {
      this.setAttribute("icon", v);
    }
    connectedCallback() {
      this.style.cssText =
        "display:inline-block;width:var(--mdc-icon-size,20px);height:var(--mdc-icon-size,20px);border-radius:50%;border:2px solid currentColor;box-sizing:border-box";
    }
  },
);

const now = new Date();
const at = (days, h, m = 0) => {
  const d = new Date(now);
  d.setDate(d.getDate() + days);
  d.setHours(h, m, 0, 0);
  return d.toISOString();
};
const reminder = (rule_id, days, titles, extra = {}) => ({
  id: `${rule_id}__${days}`,
  rule_id,
  day: at(days, 0).slice(0, 10),
  start: at(days, 0),
  end: at(days + 1, 0),
  state: "planned",
  titles,
  colors: [],
  variables: { wann: days === 1 ? "morgen" : days === 0 ? "heute" : "bald" },
  reminded_at: null,
  finished_at: null,
  acknowledged_by: null,
  acknowledged_via: null,
  snoozed_until: null,
  next_reminder_at: at(days - 1, 17),
  ...extra,
});

const muell = {
  id: "muell",
  name: "Müll rausstellen",
  icon: "mdi:trash-can-outline",
  color: "#4ad295",
  enabled: true,
  sources: ["calendar.abfallkalender"],
  filter: {
    all_day: true,
    keywords: {
      columns: ["tonne", "farbe", "artikel"],
      rows: [
        { match: "Papier", tonne: "Papiertonne", farbe: "blau", artikel: "die" },
        { match: "Bio", tonne: "Biotonne", farbe: "grün", artikel: "die" },
        { match: "Rest", tonne: "Restmülltonne", farbe: "grau", artikel: "die" },
        { match: "Gelb", tonne: "gelben Sack", farbe: "gelb", artikel: "den" },
      ],
    },
  },
  reminders: [{ at: "-1d 17:00" }],
  signals: [
    {
      id: "push",
      type: "notify",
      enabled: true,
      when: "now",
      audience: "present",
      title: "{wann}: {tonnen}",
      message: "Bitte heute Abend rausstellen.",
      actions: [
        { ack: true, label: "Steht draußen" },
        { snooze: "3h", label: "Später" },
      ],
    },
    {
      id: "lampe",
      type: "light_signal",
      enabled: true,
      entities: ["light.stehleuchte"],
      pattern: { effect: "blink", count: 3 },
      color_from: "farbe",
      when: { opportunity: [{ trigger: "state", entity_id: "light.stehleuchte", to: "on" }], manual_only: true },
      limit: { per_reminder: 1 },
      quiet: [{ from: "00:00", to: "10:00", mode: "skip" }],
      restore: true,
    },
    {
      id: "ansage",
      type: "announce",
      enabled: false,
      players: ["media_player.sonos_wohnzimmer"],
      volume: 45,
      text: "Stell endlich die {tonne} raus!",
      text_plural: "Stell endlich die {tonnen} raus!",
      when: { opportunity: [{ trigger: "state", entity_id: "binary_sensor.haustuer", to: "on" }] },
      limit: { per_reminder: 1 },
      quiet: [{ from: "22:00", to: "08:00", mode: "skip" }],
    },
  ],
  acknowledge: [{ type: "notify_action" }, { type: "tag", tag_id: "tonne" }],
  ack_label: "Steht draußen",
  repeat: "none",
  bundle: true,
  expire: "event_day 12:00",
  status: {
    state: "reminded",
    current: "muell__1",
    errors: {},
    next_event: null,
    reminders: [
      reminder("muell", 1, ["Papier", "Bio"], {
        state: "reminded",
        reminded_at: at(0, 17),
        colors: ["#0000ff", "#008000"],
        variables: { wann: "morgen", tonnen: "Papiertonne und Biotonne" },
      }),
      reminder("muell", 8, ["Rest"], { colors: ["#808080"] }),
    ],
  },
};

const kult = {
  ...muell,
  id: "kult61",
  name: "Kult61-Dienst",
  icon: "mdi:glass-cocktail",
  color: "#ff8b4a",
  sources: ["calendar.kult61"],
  filter: { all_day: false, keywords: { columns: [], rows: [{ match: "Dienst:", mode: "startswith" }] } },
  reminders: [{ at: "-1d 20:00" }, { at: "-2h" }],
  signals: [],
  ack_label: null,
  status: {
    state: "done",
    current: null,
    errors: {},
    next_event: null,
    reminders: [
      reminder("kult61", 3, ["Dienst: Theke"], { next_reminder_at: at(2, 20) }),
      reminder("kult61", 0, ["Dienst: Kasse"], {
        state: "done",
        finished_at: at(0, 9, 12),
        acknowledged_by: "Steven",
        acknowledged_via: "tag",
      }),
    ],
  },
};

const geburtstage = {
  ...muell,
  id: "geburtstage",
  name: "Geburtstage",
  icon: "mdi:cake-variant-outline",
  color: "#c58cff",
  enabled: false,
  filter: { all_day: true, keywords: { columns: [], rows: [] } },
  signals: [],
  status: { state: "inactive", current: null, errors: {}, next_event: null, reminders: [] },
};

let rules = page === "empty" ? [] : [muell, kult, geburtstage];
if (page === "done") muell.status.reminders = muell.status.reminders.slice(1);

const preview = {
  events: [
    { id: "a", day: "", start: at(1, 0), end: at(2, 0), titles: ["Bio", "Papier"], days_until: 1, colors: ["#008000", "#0000ff"], all_day: true, variables: { wann: "morgen", tonne: "Biotonne", tonnen: "Biotonne und Papiertonne", artikel: "die" }, reminder_times: [at(0, 17)] },
    { id: "b", day: "", start: at(8, 0), end: at(9, 0), titles: ["Rest"], days_until: 8, colors: ["#808080"], all_day: true, variables: {} },
    { id: "c", day: "", start: at(10, 0), end: at(11, 0), titles: ["Gelb"], days_until: 10, colors: ["#ffff00"], all_day: true, variables: {} },
  ],
  total_events: 6,
  errors: {},
  variables: [],
};

const listeners = new Set();
const hass = {
  states: {},
  locale: { language: params.get("lang") ?? "de" },
  language: params.get("lang") ?? "de",
  config: { time_zone: "Europe/Berlin" },
  themes: { darkMode: params.get("theme") !== "light" },
  user: { is_admin: params.get("admin") !== "0", name: "Steven" },
  connection: {
    subscribeMessage(cb) {
      listeners.add(cb);
      setTimeout(() => cb({ event: "init", rules }), 10);
      return Promise.resolve(() => listeners.delete(cb));
    },
  },
  async callWS(msg) {
    console.log("callWS", msg);
    if (msg.type === "laeutwerk/preview") return preview;
    if (msg.type === "laeutwerk/rules/list") return { rules };
    if (msg.type === "laeutwerk/templates/list") {
      return {
        templates: [
          { id: "builtin_muell", name: "Müll rausstellen", description: "Abfallkalender: am Vorabend erinnern, bis die Tonne draußen steht.", builtin: true, rule: { name: "Müll rausstellen", icon: "mdi:trash-can-outline", color: "#4ad295", reminders: [{ at: "-1d 18:00" }] } },
          { id: "builtin_geburtstag", name: "Geburtstage", description: "Geburtstagskalender: eine Woche vorher und am Tag selbst.", builtin: true, rule: { name: "Geburtstage", icon: "mdi:cake-variant-outline", color: "#c58cff", reminders: [{ at: "-7d 09:00" }] } },
          { id: "builtin_wartung", name: "Wartung", description: "Alle 90 Tage nach dem letzten Erledigen, täglich bis erledigt.", builtin: true, rule: { name: "Filter tauschen", icon: "mdi:air-filter", color: "#6fa8ff", interval: { every: 90 }, reminders: [{ at: "18:00" }] } },
          { id: "user_tonnen", name: "Meine Tonnen", description: "", builtin: false, rule: { name: "Tonnen", reminders: [{ at: "-1d 17:00" }] } },
        ],
      };
    }
    if (msg.type === "laeutwerk/history") {
      return {
        history: [
          { reminder_id: "h1", day: at(-6, 0).slice(0, 10), titles: ["Rest"], state: "done", finished_at: at(-7, 20, 41), acknowledged_by: "Steven", acknowledged_via: "tag", signals_sent: 2 },
          { reminder_id: "h2", day: at(-13, 0).slice(0, 10), titles: ["Papier", "Bio"], state: "missed", finished_at: at(-13, 12), acknowledged_by: null, acknowledged_via: null, signals_sent: 3 },
          { reminder_id: "h3", day: at(-20, 0).slice(0, 10), titles: ["Gelb"], state: "done", finished_at: at(-21, 18, 5), acknowledged_by: null, acknowledged_via: "notify_action", signals_sent: 1 },
        ],
      };
    }
    return msg.rule ?? {};
  },
  async callService(domain, service, data) {
    console.log("callService", domain, service, data);
  },
};

await import("../../custom_components/laeutwerk/frontend/laeutwerk-card.js");
const card = document.querySelector("laeutwerk-card");
await customElements.whenDefined("laeutwerk-card");
card.setConfig({ type: "custom:laeutwerk-card", compact: page === "compact", ...(page === "rule" ? { view: "rule", rule: "muell" } : {}) });
card.hass = hass;
document.body.dataset.ready = "1";
if (page === "templates") {
  await new Promise((r) => setTimeout(r, 50));
  card._picking = true;
}
if (page === "advanced") {
  muell.escalation = [{ after: "2h" }, { after: "21:30" }];
  muell.assignee = { persons: ["person.steven", "person.anna"], rotation: "per_event" };
  muell.activation = { conditions: [], match: "all", season: { from: "04-01", to: "11-30" } };
  muell.status.assignee_stats = { Steven: 5, Anna: 3 };
  await new Promise((r) => setTimeout(r, 50));
  card._editing = muell;
  await card.updateComplete;
  const editor = card.shadowRoot.querySelector("laeutwerk-rule-editor");
  await editor.updateComplete;
  editor.shadowRoot.querySelectorAll("section")[6]?.scrollIntoView();
}
if (page === "editor" || page === "signal") {
  await new Promise((r) => setTimeout(r, 50));
  card._editing = muell;
  await card.updateComplete;
  if (page === "signal") {
    const editor = card.shadowRoot.querySelector("laeutwerk-rule-editor");
    await editor.updateComplete;
    editor._signal = { index: 1, signal: JSON.parse(JSON.stringify(muell.signals[1])) };
  }
}
