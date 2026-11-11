"""Owns all rules: storage, runners, CRUD and change notifications."""

from __future__ import annotations

from collections.abc import Callable
import copy
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import CALLBACK_TYPE, Context, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from .compat import vol
from .const import (
    ACK_VIA_NOTIFICATION,
    ACTION_ACK_PREFIX,
    DOMAIN,
    REFRESH_MINUTES,
    SIGNAL_RULE_STATUS,
)
from .engine import RuleRunner
from .matching import Occurrence, sample_occurrence
from .model import STATE_INACTIVE, Reminder, Rule, Signal
from .schema import (
    async_validate_rule,
    make_rule_id,
    validate_rule,
    validate_signal,
)
from .signals import async_clear_notifications, async_send_signal
from .store import LaeutwerkStore, StoredData

_LOGGER = logging.getLogger(__name__)

EVENT_ADDED = "added"
EVENT_UPDATED = "updated"
EVENT_REMOVED = "removed"

MOBILE_APP_ACTION_EVENT = "mobile_app_notification_action"

RuleListener = Callable[[str, str], None]


class RuleNotFoundError(HomeAssistantError):
    """Raised for an unknown rule id."""


def person_name(hass: HomeAssistant, user_id: str | None) -> str | None:
    """Name of the person that belongs to a Home Assistant user."""
    if user_id is None:
        return None
    for state in hass.states.async_all("person"):
        if state.attributes.get("user_id") == user_id:
            return state.name
    return None


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
        self._invalid: list[dict[str, Any]] = []  # kept so nothing is lost
        self._listeners: list[RuleListener] = []
        self._started = False
        self._unsubs: list[CALLBACK_TYPE] = []
        self._unsub_started: CALLBACK_TYPE | None = None

    # ---------------------------------------------------------------- setup

    async def async_setup(self) -> None:
        """Load rules; runners start once Home Assistant has started."""
        data = await self.store.async_load()
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
        if not rule.enabled:
            return
        runner = RuleRunner(
            self.hass,
            rule,
            self.reminders.setdefault(rule.id, {}),
            on_update=self._runner_updated,
            on_changed=self.async_schedule_save,
        )
        self.runners[rule.id] = runner
        await runner.async_start()

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
        await self._async_stop_runner(rule_id, drop_open=not rule.enabled)
        self.rules[rule_id] = rule
        self.async_schedule_save()
        if self._started:
            await self._async_start_runner(rule)
        self._notify(EVENT_UPDATED, rule_id)
        return rule

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
        self._notify(EVENT_UPDATED, rule_id)

    async def async_delete_rule(self, rule_id: str) -> None:
        """Remove a rule, its reminders and its device."""
        self.get_rule(rule_id)
        await self._async_stop_runner(rule_id, drop_open=True)
        del self.rules[rule_id]
        self.reminders.pop(rule_id, None)
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
    ) -> list[Reminder]:
        """Acknowledge the reminders of one rule or all reminding ones."""
        if rule_id is not None:
            self.get_rule(rule_id)
            runner = self.runners.get(rule_id)
            if runner is None:
                return []
            return await runner.async_acknowledge(
                reminder_id=reminder_id, by=by, via=via
            )
        done: list[Reminder] = []
        for runner in list(self.runners.values()):
            if reminder_id is not None and reminder_id not in runner.reminders:
                continue
            done += await runner.async_acknowledge(
                reminder_id=reminder_id, by=by, via=via, early=False
            )
        return done

    async def async_test_signal(
        self,
        rule_id: str,
        signal_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> bool:
        """Send one signal now (saved one by id, or an unsaved configuration).

        Uses the open reminder, else the next matching event, else a sample
        event for tomorrow. Limits, quiet times and conditions are ignored.
        """
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
        return await async_send_signal(runner.signal_run(signal, test_item, Context()))

    async def _async_notification_action(self, event: Event[Any]) -> None:
        """Handle a pressed button of a push notification."""
        action = str(event.data.get("action", ""))
        if not action.startswith(ACTION_ACK_PREFIX):
            return
        await self.async_acknowledge(
            reminder_id=action.removeprefix(ACTION_ACK_PREFIX),
            by=person_name(self.hass, event.context.user_id),
            via=ACK_VIA_NOTIFICATION,
        )

    # ---------------------------------------------------------------- status

    def reminder_payload(self, rule_id: str, reminder: Reminder) -> dict[str, Any]:
        """Serialise a reminder with its variables and times."""
        runner = self.runners.get(rule_id)
        payload = reminder.to_dict()
        payload["titles"] = [event.summary for event in reminder.events]
        if runner is not None:
            next_time = runner.next_reminder_time(reminder)
            payload["variables"] = runner.variables(reminder)
            payload["expires_at"] = runner.expire_at(reminder).isoformat()
            payload["next_reminder_at"] = next_time.isoformat() if next_time else None
        return payload

    def status(self, rule_id: str) -> dict[str, Any]:
        """Runtime status of a rule (services, websocket, diagnostics)."""
        runner = self.runners.get(rule_id)
        if runner is None:
            return {
                "state": STATE_INACTIVE,
                "current": None,
                "reminders": [],
                "next_event": None,
                "errors": {},
            }
        current = runner.current()
        return {
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
    return {
        "id": occurrence.id,
        "day": occurrence.day.isoformat(),
        "start": occurrence.start.isoformat(),
        "end": occurrence.end.isoformat(),
        "titles": [event.summary for event in occurrence.events],
        "days_until": (occurrence.day - today).days,
        "variables": runner.variables(occurrence),
    }
