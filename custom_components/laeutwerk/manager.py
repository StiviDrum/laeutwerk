"""Owns all rules: storage, runners, CRUD and change notifications."""

from __future__ import annotations

from collections.abc import Callable
import copy
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import (
    CALLBACK_TYPE,
    Context,
    Event,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from .compat import vol
from .const import (
    ACK_VIA_NOTIFICATION,
    ACTION_ACK_PREFIX,
    ACTION_SNOOZE_PREFIX,
    DOMAIN,
    HISTORY_MAX,
    LOOKAHEAD_DAYS,
    REFRESH_MINUTES,
    SIGNAL_RULE_STATUS,
)
from .engine import RuleRunner
from .issues import async_check_rule, async_clear_rule
from .matching import (
    Occurrence,
    build_occurrences,
    hit_badges,
    match_event,
    render_headline,
    sample_occurrence,
)
from .model import STATE_INACTIVE, Reminder, Rule, Signal
from .schema import (
    async_validate_rule,
    make_rule_id,
    validate_rule,
    validate_signal,
)
from .signals import async_clear_notifications, async_send_signal
from .sources import async_fetch_events
from .store import LaeutwerkStore, StoredData
from .templates import (
    RUNTIME_KEYS,
    builtin_templates,
    export_yaml,
    parse_rules_yaml,
    template_from_rule,
)
from .timespec import local_instant
from .triggers import own_context

_LOGGER = logging.getLogger(__name__)

EVENT_ADDED = "added"
EVENT_UPDATED = "updated"
EVENT_REMOVED = "removed"
EVENT_REORDERED = "reordered"

# Event titles offered as keyword suggestions: look-ahead and maximum.
SUGGEST_DAYS = 60
MAX_SUGGESTIONS = 40

MOBILE_APP_ACTION_EVENT = "mobile_app_notification_action"

RuleListener = Callable[[str, str], None]


class RuleNotFoundError(HomeAssistantError):
    """Raised for an unknown rule id."""


def _person_of_user(hass: HomeAssistant, user_id: str) -> State | None:
    for state in hass.states.async_all("person"):
        if state.attributes.get("user_id") == user_id:
            return state
    return None


async def async_who(
    hass: HomeAssistant, context: Context | None
) -> tuple[str | None, str | None]:
    """Who acted: (name, person entity id).

    The person linked to the user, else the user's display name (no person).
    Nobody for system users, automations / scripts (context with a parent)
    and calls without a user.
    """
    if context is None or context.parent_id is not None or context.user_id is None:
        return None, None
    if (person := _person_of_user(hass, context.user_id)) is not None:
        return person.name, person.entity_id
    user = await hass.auth.async_get_user(context.user_id)
    if user is None or user.system_generated or not user.name:
        return None, None
    return user.name, None


def named_person(hass: HomeAssistant, value: str) -> tuple[str, str | None]:
    """Resolve an explicitly given name (service field): person entity or name."""
    if (state := hass.states.get(value)) is not None and state.domain == "person":
        return state.name, state.entity_id
    for person in hass.states.async_all("person"):
        if person.name == value:
            return person.name, person.entity_id
    return value, None


class LaeutwerkManager:
    """Central object stored in ``entry.runtime_data``."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialise the manager."""
        self.hass = hass
        self.entry_id = entry_id
        self.store = LaeutwerkStore(hass)
        self.rules: dict[str, Rule] = {}
        self.runners: dict[str, RuleRunner] = {}
        self.reminders: dict[str, dict[str, Reminder]] = {}
        self.history: dict[str, list[dict[str, Any]]] = {}
        self.templates: list[dict[str, Any]] = []
        self._invalid: list[dict[str, Any]] = []  # kept so nothing is lost
        self._listeners: list[RuleListener] = []
        self._started = False
        self._unsubs: list[CALLBACK_TYPE] = []
        self._unsub_started: CALLBACK_TYPE | None = None

    # ---------------------------------------------------------------- setup

    async def async_setup(self) -> None:
        """Load rules; runners start once Home Assistant has started."""
        data = await self.store.async_load()
        self.history = data["history"]
        self.templates = data["templates"]
        for raw in data["rules"]:
            try:
                rule = Rule.from_dict(validate_rule(raw))
            except (vol.Invalid, KeyError, ValueError) as err:
                _LOGGER.error("Ignoring invalid stored rule %s: %s", raw.get("id"), err)
                self._invalid.append(raw)
                continue
            self.rules[rule.id] = rule
            self.reminders[rule.id] = {}
            for item in data["reminders"].get(rule.id, []):
                try:
                    reminder = Reminder.from_dict(item)
                except (KeyError, ValueError) as err:
                    _LOGGER.warning("Dropping invalid stored reminder: %s", err)
                    continue
                self.reminders[rule.id][reminder.id] = reminder
        self._unsubs.append(
            self.hass.bus.async_listen(
                MOBILE_APP_ACTION_EVENT, self._async_notification_action
            )
        )
        self._unsub_started = async_at_started(self.hass, self._async_hass_started)

    async def _async_hass_started(self, _hass: HomeAssistant) -> None:
        self._unsub_started = None
        self._started = True
        for rule in list(self.rules.values()):
            await self._async_start_runner(rule)
        self._unsubs.append(
            async_track_time_interval(
                self.hass, self._async_interval, timedelta(minutes=REFRESH_MINUTES)
            )
        )
        self._unsubs.append(
            self.hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED, self._async_registry_updated
            )
        )

    @callback
    def _async_registry_updated(self, _event: Event[Any]) -> None:
        """Entities were added, removed or renamed: re-check rule references."""
        for rule in self.rules.values():
            async_check_rule(self.hass, rule)

    async def _async_interval(self, _now: datetime) -> None:
        for runner in list(self.runners.values()):
            await runner.async_refresh()

    async def async_unload(self) -> None:
        """Stop everything and flush storage."""
        if self._unsub_started:
            self._unsub_started()
            self._unsub_started = None
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        for runner in list(self.runners.values()):
            await runner.async_stop()
        self.runners.clear()
        await self.store.async_save(self._data())
        self._started = False

    # -------------------------------------------------------------- helpers

    def _data(self) -> StoredData:
        return {
            "rules": [rule.to_dict() for rule in self.rules.values()] + self._invalid,
            "history": self.history,
            "templates": self.templates,
            "reminders": {
                rule_id: [reminder.to_dict() for reminder in reminders.values()]
                for rule_id, reminders in self.reminders.items()
            },
        }

    @callback
    def async_schedule_save(self) -> None:
        """Debounced save of rules + reminders."""
        self.store.async_schedule_save(self._data)

    @callback
    def async_add_listener(self, listener: RuleListener) -> CALLBACK_TYPE:
        """Listen for rule added/updated/removed events."""
        self._listeners.append(listener)

        @callback
        def remove() -> None:
            self._listeners.remove(listener)

        return remove

    @callback
    def _notify(self, event: str, rule_id: str) -> None:
        async_dispatcher_send(self.hass, SIGNAL_RULE_STATUS.format(rule_id))
        for listener in list(self._listeners):
            listener(event, rule_id)

    @callback
    def _runner_updated(self, runner: RuleRunner) -> None:
        self._notify(EVENT_UPDATED, runner.rule.id)

    async def _async_start_runner(self, rule: Rule) -> None:
        async_check_rule(self.hass, rule)
        if not rule.enabled:
            return
        runner = RuleRunner(
            self.hass,
            rule,
            self.reminders.setdefault(rule.id, {}),
            on_update=self._runner_updated,
            on_changed=self.async_schedule_save,
            on_finished=lambda reminder, rule_id=rule.id: self._add_history(
                rule_id, reminder
            ),
            history=lambda rule_id=rule.id: self.history.get(rule_id, []),
            on_reopened=lambda reminder, rule_id=rule.id: self._drop_history(
                rule_id, reminder.id
            ),
            household_quiet=self.household_quiet,
        )
        self.runners[rule.id] = runner
        await runner.async_start()

    def household_quiet(self) -> list[dict[str, str]]:
        """Quiet times of the whole household (integration options)."""
        entry = self.hass.config_entries.async_get_entry(self.entry_id)
        return list(entry.options.get("quiet", [])) if entry else []

    @callback
    def _add_history(self, rule_id: str, reminder: Reminder) -> None:
        """Remember a finished reminder (newest first, limited)."""
        entries = [
            e for e in self.history.get(rule_id, []) if e["reminder_id"] != reminder.id
        ]
        entries.insert(
            0,
            {
                "reminder_id": reminder.id,
                "day": reminder.day.isoformat(),
                "titles": [event.summary for event in reminder.events],
                "state": reminder.state,
                "reminded_at": (
                    reminder.reminded_at.isoformat() if reminder.reminded_at else None
                ),
                "finished_at": (
                    reminder.finished_at.isoformat() if reminder.finished_at else None
                ),
                "acknowledged_by": reminder.acknowledged_by,
                "acknowledged_via": reminder.acknowledged_via,
                "acknowledged_person": reminder.acknowledged_person,
                "signals_sent": sum(reminder.signals_sent.values()),
                "assignee": reminder.assignee,
            },
        )
        self.history[rule_id] = entries[:HISTORY_MAX]
        self.async_schedule_save()

    async def async_title_suggestions(
        self, rule_data: dict[str, Any], days: int = SUGGEST_DAYS
    ) -> list[dict[str, Any]]:
        """Event titles of the rule's sources (for keyword suggestions).

        Each distinct title with how often it occurs in the next ``days`` days
        and whether the keyword table already matches it.
        """
        rule = draft_rule(rule_data)
        start, _end = lookahead_window(rule)
        events, _errors = await async_fetch_events(
            self.hass, rule.sources, start, dt_util.utcnow() + timedelta(days=days)
        )
        titles: dict[str, dict[str, Any]] = {}
        for event in sorted(events, key=lambda e: e.start):
            title = event.summary.strip()
            if not title:
                continue
            entry = titles.setdefault(
                title,
                {
                    "title": title,
                    "count": 0,
                    "matched": bool(rule.filter.rows)
                    and match_event(rule.filter, event) is not None,
                },
            )
            entry["count"] += 1
        return list(titles.values())[:MAX_SUGGESTIONS]

    async def async_reorder(self, rule_ids: list[str]) -> None:
        """Put the rules in this order (rules not listed keep theirs, after)."""
        for rule_id in rule_ids:
            self.get_rule(rule_id)
        order = list(dict.fromkeys(rule_ids)) + [
            rule_id for rule_id in self.rules if rule_id not in rule_ids
        ]
        self.rules = {rule_id: self.rules[rule_id] for rule_id in order}
        self.async_schedule_save()
        for listener in list(self._listeners):
            listener(EVENT_REORDERED, "")

    @callback
    def _drop_history(self, rule_id: str, reminder_id: str) -> None:
        """Forget the history entry of a reopened reminder."""
        entries = self.history.get(rule_id, [])
        self.history[rule_id] = [e for e in entries if e["reminder_id"] != reminder_id]
        self.async_schedule_save()

    async def async_reopen(self, reminder_id: str) -> Reminder | None:
        """Undo the acknowledgement of a reminder (any rule)."""
        for runner in list(self.runners.values()):
            if reminder_id in runner.reminders:
                return await runner.async_reopen(reminder_id)
        return None

    @property
    def invalid_rules(self) -> list[dict[str, Any]]:
        """Stored rules that could not be loaded (kept, shown in diagnostics)."""
        return list(self._invalid)

    async def _async_stop_runner(self, rule_id: str, *, drop_open: bool) -> None:
        """Stop a runner; optionally forget its open reminders."""
        runner = self.runners.pop(rule_id, None)
        if runner:
            await runner.async_stop()
        if not drop_open:
            return
        rule = self.rules.get(rule_id)
        reminders = self.reminders.get(rule_id, {})
        for reminder in [r for r in reminders.values() if r.is_open]:
            del reminders[reminder.id]
            if rule and any(reminder.signals_sent.values()):
                self.hass.async_create_task(
                    async_clear_notifications(
                        self.hass, rule.signals, reminder, context=Context()
                    )
                )

    def get_rule(self, rule_id: str) -> Rule:
        """Return a rule or raise."""
        if (rule := self.rules.get(rule_id)) is None:
            raise RuleNotFoundError(f"Unknown rule '{rule_id}'")
        return rule

    # ------------------------------------------------------------------ CRUD

    async def async_create_rule(self, data: dict[str, Any]) -> Rule:
        """Validate and add a new rule."""
        data = dict(data)
        if not data.get("id"):
            data["id"] = make_rule_id(str(data.get("name", "")), set(self.rules))
        elif data["id"] in self.rules:
            raise vol.Invalid(f"a rule with id '{data['id']}' already exists")
        rule = Rule.from_dict(await async_validate_rule(self.hass, data))
        _default_interval_start(rule)
        self.rules[rule.id] = rule
        self.reminders[rule.id] = {}
        self.async_schedule_save()
        self._notify(EVENT_ADDED, rule.id)
        if self._started:
            await self._async_start_runner(rule)
        return rule

    async def async_duplicate_rule(
        self, rule_id: str, name: str | None = None, new_id: str | None = None
    ) -> Rule:
        """Copy a rule under a new id; the copy starts switched off."""
        data = copy.deepcopy(self.get_rule(rule_id).to_dict())
        copy_word = "Kopie" if self.hass.config.language.startswith("de") else "copy"
        data["name"] = name or f"{data['name']} ({copy_word})"
        data["id"] = new_id
        data["enabled"] = False
        return await self.async_create_rule(data)

    async def async_update_rule(self, rule_id: str, data: dict[str, Any]) -> Rule:
        """Replace a rule (full update); reminder state is kept."""
        self.get_rule(rule_id)
        rule = Rule.from_dict(
            await async_validate_rule(self.hass, {**data, "id": rule_id})
        )
        _default_interval_start(rule, self.rules[rule_id])
        await self._async_stop_runner(rule_id, drop_open=not rule.enabled)
        self.rules[rule_id] = rule
        self.async_schedule_save()
        if self._started:
            await self._async_start_runner(rule)
        self._notify(EVENT_UPDATED, rule_id)
        return rule

    async def async_import_rules(self, text: str) -> list[Rule]:
        """Create rules from YAML; ids that exist already get a new one."""
        items = parse_rules_yaml(text)
        prepared = []
        for item in items:
            data = {k: v for k, v in item.items() if k not in RUNTIME_KEYS}
            if data.get("id") in self.rules:
                data["id"] = None
            prepared.append(data)
        # Validate everything first: an import adds all rules or none.
        taken = set(self.rules)
        for data in prepared:
            check = dict(data)
            check["id"] = check.get("id") or make_rule_id(
                str(check.get("name", "")), taken
            )
            taken.add(check["id"])
            await async_validate_rule(self.hass, check)
        return [await self.async_create_rule(data) for data in prepared]

    def export_rules(self, rule_ids: list[str]) -> str:
        """YAML of some rules."""
        return export_yaml([self.get_rule(rule_id).to_dict() for rule_id in rule_ids])

    def list_templates(self) -> list[dict[str, Any]]:
        """Built-in templates (server language) and the user's own."""
        builtin = [
            {**t, "builtin": True} for t in builtin_templates(self.hass.config.language)
        ]
        return builtin + [{**t, "builtin": False} for t in self.templates]

    def save_template(
        self, name: str, rule: dict[str, Any], description: str = ""
    ) -> dict[str, Any]:
        """Save a rule configuration as the user's own template."""
        data = {**template_from_rule(rule), "name": rule.get("name") or name}
        data.setdefault("reminders", [{"at": "09:00"}])
        data["sources"] = data.get("sources") or []
        # Must be a valid rule apart from the personal parts.
        validate_rule(
            {**data, "id": "template", "sources": ["calendar.template"]}
            if not data.get("interval")
            else {**data, "id": "template"}
        )
        data.pop("sources", None)
        existing = {t["id"] for t in self.templates}
        template_id = make_rule_id(f"user {name}", existing)
        template = {
            "id": template_id,
            "name": name,
            "description": description,
            "rule": data,
        }
        self.templates.append(template)
        self.async_schedule_save()
        return template

    def delete_template(self, template_id: str) -> None:
        """Delete one of the user's templates."""
        if not any(t["id"] == template_id for t in self.templates):
            raise HomeAssistantError(f"Unknown template '{template_id}'")
        self.templates = [t for t in self.templates if t["id"] != template_id]
        self.async_schedule_save()

    async def async_set_enabled(self, rule_id: str, enabled: bool) -> None:
        """Switch a rule on or off (off forgets its open reminders)."""
        rule = self.get_rule(rule_id)
        if rule.enabled == enabled:
            return
        rule.enabled = enabled
        self.async_schedule_save()
        if enabled:
            if self._started:
                await self._async_start_runner(rule)
        else:
            await self._async_stop_runner(rule_id, drop_open=True)
            async_clear_rule(self.hass, rule_id)
        self._notify(EVENT_UPDATED, rule_id)

    async def async_delete_rule(self, rule_id: str) -> None:
        """Remove a rule, its reminders and its device."""
        self.get_rule(rule_id)
        await self._async_stop_runner(rule_id, drop_open=True)
        del self.rules[rule_id]
        self.reminders.pop(rule_id, None)
        self.history.pop(rule_id, None)
        async_clear_rule(self.hass, rule_id)
        self.async_schedule_save()
        self._notify(EVENT_REMOVED, rule_id)
        registry = dr.async_get(self.hass)
        for device in dr.async_entries_for_config_entry(registry, self.entry_id):
            if (DOMAIN, rule_id) in device.identifiers:
                registry.async_remove_device(device.id)

    # --------------------------------------------------------------- actions

    async def async_acknowledge(
        self,
        rule_id: str | None = None,
        *,
        reminder_id: str | None = None,
        by: str | None = None,
        via: str | None = None,
        person: str | None = None,
    ) -> list[Reminder]:
        """Acknowledge the reminders of one rule or all reminding ones."""
        if rule_id is not None:
            self.get_rule(rule_id)
            runner = self.runners.get(rule_id)
            if runner is None:
                return []
            return await runner.async_acknowledge(
                reminder_id=reminder_id, by=by, via=via, person=person
            )
        done: list[Reminder] = []
        for runner in list(self.runners.values()):
            if reminder_id is not None and reminder_id not in runner.reminders:
                continue
            done += await runner.async_acknowledge(
                reminder_id=reminder_id, by=by, via=via, person=person, early=False
            )
        return done

    async def async_snooze(
        self,
        minutes: int,
        rule_id: str | None = None,
        *,
        reminder_id: str | None = None,
    ) -> list[Reminder]:
        """Remind later: the open reminders of one rule or of all rules."""
        if rule_id is not None:
            self.get_rule(rule_id)
        snoozed: list[Reminder] = []
        for runner in list(self.runners.values()):
            if rule_id is not None and runner.rule.id != rule_id:
                continue
            snoozed += await runner.async_snooze(minutes, reminder_id=reminder_id)
        return snoozed

    async def async_test_signal(
        self,
        rule_id: str | None,
        signal_id: str | None = None,
        config: dict[str, Any] | None = None,
        rule_data: dict[str, Any] | None = None,
    ) -> bool:
        """Send one signal now (saved one by id, or an unsaved configuration).

        Uses the open reminder, else the next matching event, else a sample
        event for tomorrow. Limits, quiet times and conditions are ignored.
        With ``rule_data`` an unsaved rule (as in the editor) is used.
        """
        if rule_data is not None:
            rule = draft_rule(rule_data)
            runner = RuleRunner(
                self.hass, rule, {}, on_update=lambda _r: None, on_changed=lambda: None
            )
            events, _errors = await async_fetch_events(
                self.hass, rule.sources, *lookahead_window(rule)
            )
            now = dt_util.utcnow()
            occurrences = sorted(build_occurrences(rule, events), key=lambda o: o.start)
            item = next((o for o in occurrences if o.end > now), None) or (
                sample_occurrence(rule)
            )
            signal = Signal.from_dict({"id": "test", **validate_signal(config or {})})
            test_item = Occurrence(
                id="test",
                day=item.day,
                start=item.start,
                end=item.end,
                events=tuple(item.events),
            )
            return await async_send_signal(
                runner.signal_run(signal, test_item, own_context())
            )
        assert rule_id is not None
        rule = self.get_rule(rule_id)
        if config is not None:
            signal = Signal.from_dict({"id": "test", **validate_signal(config)})
        else:
            found = next((s for s in rule.signals if s.id == signal_id), None)
            if found is None:
                raise HomeAssistantError(
                    f"Rule '{rule_id}' has no signal '{signal_id}'"
                )
            signal = found
        runner = self.runners.get(rule_id) or RuleRunner(
            self.hass,
            rule,
            {},
            on_update=lambda _runner: None,
            on_changed=lambda: None,
        )
        item: Reminder | Occurrence | None = (
            next(iter(runner.open_reminders), None) or runner.next_occurrence()
        )
        if item is None:
            item = sample_occurrence(rule)
        test_item = Occurrence(
            id="test",
            day=item.day,
            start=item.start,
            end=item.end,
            events=tuple(item.events),
        )
        return await async_send_signal(
            runner.signal_run(signal, test_item, own_context())
        )

    async def _async_notification_action(self, event: Event[Any]) -> None:
        """Handle a pressed button of a push notification."""
        action = str(event.data.get("action", ""))
        if action.startswith(ACTION_SNOOZE_PREFIX):
            minutes, _, reminder_id = action.removeprefix(
                ACTION_SNOOZE_PREFIX
            ).partition("__")
            if minutes.isdigit() and reminder_id:
                await self.async_snooze(int(minutes), reminder_id=reminder_id)
            return
        if not action.startswith(ACTION_ACK_PREFIX):
            return
        by, person = await async_who(self.hass, event.context)
        await self.async_acknowledge(
            reminder_id=action.removeprefix(ACTION_ACK_PREFIX),
            by=by,
            via=ACK_VIA_NOTIFICATION,
            person=person,
        )

    # ---------------------------------------------------------------- status

    def reminder_payload(self, rule_id: str, reminder: Reminder) -> dict[str, Any]:
        """Serialise a reminder with its variables and times."""
        runner = self.runners.get(rule_id)
        payload = reminder.to_dict()
        payload["titles"] = [event.summary for event in reminder.events]
        if rule := self.rules.get(rule_id):
            payload["badges"] = hit_badges(rule, reminder.events)
        if runner is not None:
            next_time = runner.next_reminder_time(reminder)
            payload["variables"] = runner.variables(reminder)
            payload["headline"] = render_headline(
                runner.rule, reminder.events, payload["variables"]
            )
            payload["expires_at"] = runner.expire_at(reminder).isoformat()
            payload["next_reminder_at"] = next_time.isoformat() if next_time else None
            payload["assignee_name"] = runner.assignee_name(reminder.assignee)
            payload["substitute_for_name"] = runner.assignee_name(
                reminder.substitute_for
            )
            payload["tags"] = runner.tag_ids(reminder)
        return payload

    def assignee_stats(self, rule_id: str) -> dict[str, int]:
        """How often each person acknowledged a reminder of the rule (history)."""
        stats: dict[str, int] = {}
        for entry in self.history.get(rule_id, []):
            if entry.get("state") == "done" and (who := entry.get("acknowledged_by")):
                stats[who] = stats.get(who, 0) + 1
        return stats

    def status(self, rule_id: str) -> dict[str, Any]:
        """Runtime status of a rule (services, websocket, diagnostics)."""
        runner = self.runners.get(rule_id)
        if runner is None:
            return {
                "active": False,
                "assignee_stats": self.assignee_stats(rule_id),
                "state": STATE_INACTIVE,
                "current": None,
                "reminders": [],
                "next_event": None,
                "errors": {},
            }
        current = runner.current()
        return {
            "active": runner.active,
            "assignee_stats": self.assignee_stats(rule_id),
            "state": runner.state,
            "current": current.id if current else None,
            "reminders": [
                self.reminder_payload(rule_id, reminder)
                for reminder in sorted(runner.reminders.values(), key=lambda r: r.start)
            ],
            "next_event": occurrence_payload(runner, runner.next_occurrence()),
            "errors": dict(runner.errors),
        }


def occurrence_payload(
    runner: RuleRunner, occurrence: Occurrence | None
) -> dict[str, Any] | None:
    """Serialise the next matching event (bundle)."""
    if occurrence is None:
        return None
    today = dt_util.now().date()
    variables = runner.variables(occurrence)
    return {
        "id": occurrence.id,
        "day": occurrence.day.isoformat(),
        "start": occurrence.start.isoformat(),
        "end": occurrence.end.isoformat(),
        "titles": [event.summary for event in occurrence.events],
        "days_until": (occurrence.day - today).days,
        "badges": hit_badges(runner.rule, occurrence.events),
        "headline": render_headline(runner.rule, occurrence.events, variables),
        "tags": runner.tag_ids(occurrence),
        "all_day": all(event.all_day for event in occurrence.events),
        "variables": variables,
    }


def _default_interval_start(rule: Rule, old: Rule | None = None) -> None:
    """Without a start an interval rule is first due on the day it is saved."""
    if not rule.interval or rule.interval.get("start"):
        return
    previous = (old.interval or {}).get("start") if old else None
    rule.interval = {
        **rule.interval,
        "start": previous or dt_util.now().date().isoformat(),
    }


def draft_rule(data: dict[str, Any]) -> Rule:
    """Rule from editor data that may not be complete yet (preview, tests).

    Missing id, name and reminder times get placeholders; everything else is
    validated like a saved rule.
    """
    data = {key: value for key, value in data.items() if key != "status"}
    data.setdefault("id", "preview")
    data["id"] = data["id"] or "preview"
    data.setdefault("name", "Preview")
    data["name"] = data["name"] or "Preview"
    if not data.get("reminders"):
        data["reminders"] = [{"at": "event_day 00:00"}]
    return Rule.from_dict(validate_rule(data))


def lookahead_window(rule: Rule | None = None) -> tuple[datetime, datetime]:
    """Start of today until the rule's calendar look-ahead (UTC)."""
    now = dt_util.utcnow()
    tz = dt_util.get_default_time_zone()
    start = local_instant(now.astimezone(tz).date(), 0, tz)
    return start, now + timedelta(days=rule.lookahead_days if rule else LOOKAHEAD_DAYS)
