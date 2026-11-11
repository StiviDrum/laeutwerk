"""Runtime of one rule: find events, keep reminders, fire signals once."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timedelta, tzinfo
import logging
from typing import Any

from homeassistant.core import (
    CALLBACK_TYPE,
    Context,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.exceptions import ConditionError, HomeAssistantError
from homeassistant.helpers import (
    condition as condition_helper,
    config_validation as cv,
    script as script_helper,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.util import dt as dt_util

from .compat import vol
from .const import (
    ACK_VIA_TAG,
    ACK_VIA_TRIGGER,
    DOMAIN,
    EARLY_ACK_HOURS,
    EVENT_ACKNOWLEDGED,
    EVENT_MISSED,
    EVENT_REMINDED,
    EVENT_SIGNAL_SENT,
    EVENT_TAG_SCANNED,
    LOOKAHEAD_DAYS,
)
from .durations import duration_minutes
from .matching import Occurrence, build_occurrences, build_variables, is_plural
from .model import (
    ACK_TAG,
    ACK_TRIGGER,
    INTERVAL_SOURCE,
    MATCH_ANY,
    ROTATION_AFTER_LAST,
    ROTATION_FIXED,
    ROTATION_PER_EVENT,
    ROTATION_WEEKLY,
    STATE_DONE,
    STATE_INACTIVE,
    STATE_MISSED,
    STATE_PLANNED,
    STATE_REMINDED,
    WHEN_NOW,
    CalendarEvent,
    Reminder,
    Rule,
    Signal,
)
from .signals import (
    SignalRun,
    async_clear_notifications,
    async_conditions_met,
    async_send_signal,
    is_deferrable,
    limit_reached,
    quiet_until,
)
from .sources import TODO_DOMAIN, async_fetch_events
from .timespec import local_instant, parse_timespec, resolve
from .triggers import (
    TriggerListener,
    is_manual,
    is_own_context,
    own_context,
    person_of,
)

_LOGGER = logging.getLogger(__name__)

# Calendar entities change state when events start/end or are edited;
# several changes in a row cause one refresh.
SOURCE_DEBOUNCE = 2  # seconds
# Finished reminders are kept this long after their day (card: "done" list).
KEEP_FINISHED = timedelta(days=1)


class RuleRunner:
    """Owns the reminders of one enabled rule."""

    def __init__(
        self,
        hass: HomeAssistant,
        rule: Rule,
        reminders: dict[str, Reminder],
        *,
        on_update: Callable[[RuleRunner], None],
        on_changed: Callable[[], None],
        on_finished: Callable[[Reminder], None] | None = None,
        history: Callable[[], list[dict[str, Any]]] | None = None,
    ) -> None:
        """Initialise; ``reminders`` is the persisted dict owned by the manager."""
        self.hass = hass
        self.rule = rule
        self.reminders = reminders
        self.upcoming: list[Occurrence] = []
        self.errors: dict[str, str] = {}
        self._on_update = on_update
        self._on_changed = on_changed
        self._on_finished = on_finished
        self._history = history or list
        # Activation (0.6): False while the rule's conditions are not met.
        self.active = True
        self._activation: list[Callable[[HomeAssistant], bool | None]] = []
        self._on_done: script_helper.Script | None = None
        self._lock = asyncio.Lock()
        self._unsub_timer: CALLBACK_TYPE | None = None
        self._unsub_sources: CALLBACK_TYPE | None = None
        self._unsub_debounce: CALLBACK_TYPE | None = None
        self._stopped = False
        self._sending: set[tuple[str, str]] = set()
        # Triggers that only listen while a reminder needs them.
        self._opportunities: list[TriggerListener] = []
        self._ack_triggers: list[tuple[TriggerListener, bool]] = []
        self._unsub_tags: CALLBACK_TYPE | None = None

    # ------------------------------------------------------------ lifecycle

    async def async_start(self) -> None:
        """Start listening to the source calendars and read them once."""
        watched = set(self.rule.sources)
        watched |= await self._async_compile_activation()
        await self._async_compile_on_done()
        if watched:
            self._unsub_sources = async_track_state_change_event(
                self.hass, list(watched), self._async_source_changed
            )
        self._setup_listeners()
        await self.async_refresh()

    async def _async_compile_activation(self) -> set[str]:
        """Compile the activation conditions; return the entities they use."""
        conditions = (self.rule.activation or {}).get("conditions") or []
        entities: set[str] = set()
        try:
            validated = await condition_helper.async_validate_conditions_config(
                self.hass, cv.CONDITIONS_SCHEMA(conditions)
            )
            for config in validated:
                self._activation.append(
                    await condition_helper.async_from_config(self.hass, config)
                )
                entities |= condition_helper.async_extract_entities(config)
        except (vol.Invalid, HomeAssistantError) as err:
            _LOGGER.warning("Rule %s: activation conditions: %s", self.rule.id, err)
        return entities

    async def _async_compile_on_done(self) -> None:
        if not self.rule.on_done:
            return
        try:
            sequence = await script_helper.async_validate_actions_config(
                self.hass, cv.SCRIPT_SCHEMA(self.rule.on_done)
            )
        except (vol.Invalid, HomeAssistantError) as err:
            _LOGGER.warning("Rule %s: on_done actions: %s", self.rule.id, err)
            return
        self._on_done = script_helper.Script(
            self.hass,
            sequence,
            f"{self.rule.name}: on_done",
            DOMAIN,
            script_mode=script_helper.SCRIPT_MODE_PARALLEL,
            logger=_LOGGER,
        )

    def _is_active(self) -> bool:
        """Activation conditions (all / any) as of now."""
        if not self._activation:
            return True
        results = []
        for checker in self._activation:
            try:
                results.append(checker(self.hass) is True)
            except (ConditionError, HomeAssistantError) as err:
                _LOGGER.warning("Rule %s: activation: %s", self.rule.id, err)
                results.append(False)
        if (self.rule.activation or {}).get("match") == MATCH_ANY:
            return any(results)
        return all(results)

    def in_season(self, day: date) -> bool:
        """Whether a day is inside the rule's season (always without one)."""
        season = (self.rule.activation or {}).get("season")
        if not season:
            return True
        key = f"{day.month:02d}-{day.day:02d}"
        start, end = season["from"], season["to"]
        if start <= end:
            return start <= key <= end
        return key >= start or key <= end  # across the turn of the year

    async def async_stop(self) -> None:
        """Cancel timers and listeners."""
        self._stopped = True
        if self._on_done is not None:
            await self._on_done.async_stop()
        for listener in [*self._opportunities, *(a for a, _ in self._ack_triggers)]:
            listener.update(False)
        for attr in (
            "_unsub_timer",
            "_unsub_sources",
            "_unsub_debounce",
            "_unsub_tags",
        ):
            if unsub := getattr(self, attr):
                unsub()
                setattr(self, attr, None)

    def _setup_listeners(self) -> None:
        """Prepare opportunity and acknowledge triggers (attached on demand)."""
        rule = self.rule
        for signal in rule.signals:
            if not signal.enabled or signal.opportunity is None:
                continue

            async def opportunity(
                variables: dict[str, Any],
                context: Context | None = None,
                signal: Signal = signal,
            ) -> None:
                self._async_opportunity(signal, variables, context)

            self._opportunities.append(
                TriggerListener(
                    self.hass,
                    f"{rule.name}: {signal.id}",
                    signal.opportunity,
                    opportunity,
                )
            )
        tags: set[str] = set()
        for ack in rule.acknowledge:
            if ack["type"] == ACK_TAG:
                tags.add(ack["tag_id"])
            elif ack["type"] == ACK_TRIGGER:
                early = bool(ack.get("early"))

                async def acknowledge(
                    variables: dict[str, Any],
                    context: Context | None = None,
                    early: bool = early,
                ) -> None:
                    await self.async_acknowledge(
                        by=person_of(self.hass, variables, context) or None,
                        via=ACK_VIA_TRIGGER,
                        early=early,
                    )

                self._ack_triggers.append(
                    (
                        TriggerListener(
                            self.hass,
                            f"{rule.name}: acknowledge",
                            ack["trigger"],
                            acknowledge,
                        ),
                        early,
                    )
                )
        if tags:

            async def tag_scanned(event: Event[Any]) -> None:
                if event.data.get("tag_id") in tags:
                    await self.async_acknowledge(
                        by=person_of(self.hass, {}, event.context) or None,
                        via=ACK_VIA_TAG,
                    )

            self._unsub_tags = self.hass.bus.async_listen(
                EVENT_TAG_SCANNED, tag_scanned
            )

    def _sync_listeners(self) -> None:
        """Listen to triggers only while a reminder can use them."""
        if self._stopped:
            return
        reminding = any(r.state == STATE_REMINDED for r in self.reminders.values())
        has_open = any(r.is_open for r in self.reminders.values())
        for listener in self._opportunities:
            listener.update(reminding)
        for listener, early in self._ack_triggers:
            listener.update(reminding or (early and has_open))

    @callback
    def _async_opportunity(
        self, signal: Signal, variables: dict[str, Any], context: Context | None
    ) -> None:
        """Send a signal for the open reminders after its trigger fired."""
        if is_own_context(context):
            return
        if signal.manual_only and not is_manual(context):
            return
        person = person_of(self.hass, variables, context)
        for reminder in self.open_reminders:
            if signal.stage <= reminder.stage:
                self._dispatch(signal, reminder, extra={"person": person})
        self._on_changed()

    @callback
    def _async_source_changed(self, _event: Event[EventStateChangedData]) -> None:
        if self._unsub_debounce:
            self._unsub_debounce()

        @callback
        def _refresh(_now: datetime) -> None:
            self._unsub_debounce = None
            self.hass.async_create_task(self.async_refresh())

        self._unsub_debounce = async_call_later(self.hass, SOURCE_DEBOUNCE, _refresh)

    # ----------------------------------------------------------- time helpers

    def _instant(self, text: str, item: Reminder | Occurrence) -> datetime:
        return resolve(
            parse_timespec(text),
            day=item.day,
            start=item.start,
            end=item.end,
            tz=dt_util.get_default_time_zone(),
        )

    def expire_at(self, item: Reminder | Occurrence) -> datetime:
        """When an open reminder counts as missed."""
        return self._instant(self.rule.expire, item)

    def reminder_times(self, item: Reminder | Occurrence) -> list[tuple[str, datetime]]:
        """All reminder times of a reminder: (text form, UTC instant)."""
        return [(at, self._instant(at, item)) for at in self.rule.reminders]

    def next_reminder_time(self, reminder: Reminder) -> datetime | None:
        """Next reminder time that was not sent yet."""
        times = [
            when
            for at, when in self.reminder_times(reminder)
            if at not in reminder.fired
        ]
        return min(times) if times else None

    # ---------------------------------------------------------------- refresh

    async def async_refresh(self) -> None:
        """Read the calendars, reconcile reminders, then process due times."""
        if self._stopped:
            return
        async with self._lock:
            now = dt_util.utcnow()
            tz = dt_util.get_default_time_zone()
            today = now.astimezone(tz).date()
            events, errors = await async_fetch_events(
                self.hass,
                self.rule.sources,
                local_instant(today, 0, tz),
                now + timedelta(days=LOOKAHEAD_DAYS),
            )
            if self._stopped:
                return
            if errors != self.errors:
                for entity_id, error in errors.items():
                    _LOGGER.warning(
                        "Rule %s: cannot read %s: %s", self.rule.id, entity_id, error
                    )
            self.errors = errors
            if self.rule.interval:
                events.append(self._interval_event(today, tz))
            events = [self._carry(event, today, tz) for event in events]
            self.active = self._is_active()
            occurrences = sorted(
                (
                    o
                    for o in build_occurrences(self.rule, events)
                    if self.in_season(o.day)
                ),
                key=lambda o: o.start,
            )
            self.upcoming = occurrences
            if not self.active:
                occurrences = []
            changed = self._reconcile(occurrences, now, today, complete=not errors)
            changed = self._process(now) or changed
        self._finish(changed, force_update=True)

    def last_done(self) -> datetime | None:
        """When a reminder of this rule was last acknowledged (history)."""
        for entry in self._history():
            if entry.get("state") == STATE_DONE and entry.get("finished_at"):
                return dt_util.parse_datetime(entry["finished_at"])
        return None

    def _interval_event(self, today: date, tz: tzinfo) -> CalendarEvent:
        """Return the next due day of an "interval since done" rule as an event."""
        interval = self.rule.interval or {}
        last = self.last_done()
        if last is not None:
            due = last.astimezone(tz).date() + timedelta(days=int(interval["every"]))
        else:
            start = interval.get("start")
            due = date.fromisoformat(str(start)) if start else today
        return CalendarEvent(
            calendar=INTERVAL_SOURCE,
            summary=self.rule.name,
            start=local_instant(due, 0, tz),
            end=local_instant(due + timedelta(days=1), 0, tz),
            all_day=True,
            day=due,
        )

    @staticmethod
    def _carry(event: CalendarEvent, today: date, tz: tzinfo) -> CalendarEvent:
        """Overdue to-dos and intervals stay due: shown as an event of today."""
        domain = event.calendar.split(".", 1)[0]
        if domain not in (TODO_DOMAIN, INTERVAL_SOURCE) or event.day >= today:
            return event
        return replace(
            event,
            day=today,
            start=local_instant(today, 0, tz),
            end=local_instant(today + timedelta(days=1), 0, tz),
            all_day=True,
        )

    def _assign(self, occurrence: Occurrence) -> str | None:
        """Responsible person (entity id) for a new reminder."""
        assignee = self.rule.assignee
        if not assignee:
            return None
        persons: list[str] = assignee["persons"]
        rotation = assignee.get("rotation", ROTATION_FIXED)
        if rotation == ROTATION_WEEKLY:
            return persons[((occurrence.day.toordinal() - 1) // 7) % len(persons)]
        if rotation == ROTATION_PER_EVENT:
            earlier = sum(
                1
                for r in self.reminders.values()
                if r.assignee is not None and r.is_open and r.start < occurrence.start
            )
            return persons[(len(self._history()) + earlier) % len(persons)]
        if rotation == ROTATION_AFTER_LAST:
            names = {
                entity_id: (
                    state.name if (state := self.hass.states.get(entity_id)) else ""
                )
                for entity_id in persons
            }
            last = next(
                (
                    e.get("acknowledged_by")
                    for e in self._history()
                    if e.get("state") == STATE_DONE and e.get("acknowledged_by")
                ),
                None,
            )
            for index, entity_id in enumerate(persons):
                if last and names[entity_id] == last:
                    return persons[(index + 1) % len(persons)]
        return persons[0]

    def assignee_name(self, entity_id: str | None) -> str | None:
        """Display name of a responsible person."""
        if entity_id is None:
            return None
        state = self.hass.states.get(entity_id)
        return state.name if state else entity_id.split(".", 1)[-1]

    def _reconcile(
        self,
        occurrences: list[Occurrence],
        now: datetime,
        today: Any,
        *,
        complete: bool,
    ) -> bool:
        changed = False
        known = {occurrence.id for occurrence in occurrences}
        for occurrence in occurrences:
            reminder = self.reminders.get(occurrence.id)
            if reminder is None:
                if self.expire_at(occurrence) <= now:
                    continue  # already over when it was found: nothing to remind
                self.reminders[occurrence.id] = Reminder(
                    id=occurrence.id,
                    rule_id=self.rule.id,
                    day=occurrence.day,
                    start=occurrence.start,
                    end=occurrence.end,
                    events=list(occurrence.events),
                    assignee=self._assign(occurrence),
                )
                changed = True
            elif reminder.is_open and complete:
                events = list(occurrence.events)
                if reminder.events != events:
                    reminder.events = events
                    reminder.start, reminder.end = occurrence.start, occurrence.end
                    changed = True
        if not complete:
            return changed  # a calendar failed: do not drop anything
        for reminder in list(self.reminders.values()):
            if reminder.id in known:
                continue
            active = (
                reminder.state == STATE_REMINDED or reminder.snoozed_until is not None
            )
            if (reminder.is_open and not active) or (active and reminder.day >= today):
                # Event was removed or moved.
                self._drop(reminder)
                changed = True
            elif not reminder.is_open and reminder.day + KEEP_FINISHED < today:
                del self.reminders[reminder.id]
                changed = True
        return changed

    def _drop(self, reminder: Reminder) -> None:
        del self.reminders[reminder.id]
        if reminder.state == STATE_REMINDED:
            self._clear_notifications(reminder)

    # ---------------------------------------------------------------- process

    async def async_process(self) -> None:
        """Handle due reminder times and expiries (timer callback)."""
        if self._stopped:
            return
        async with self._lock:
            changed = self._process(dt_util.utcnow())
        self._finish(changed)

    def _process(self, now: datetime) -> bool:
        changed = False
        next_time: datetime | None = None
        for reminder in sorted(self.reminders.values(), key=lambda r: r.start):
            if not reminder.is_open:
                continue
            expire = self.expire_at(reminder)
            if now >= expire:
                reminder.state = STATE_MISSED
                reminder.finished_at = now
                reminder.deferred.clear()
                self._fire(EVENT_MISSED, reminder)
                self._clear_notifications(reminder)
                changed = True
                continue
            times = self.reminder_times(reminder)
            due = [at for at, when in times if when <= now and at not in reminder.fired]
            if reminder.snoozed_until is not None:
                # "Later": regular reminder times in between are skipped.
                reminder.fired.extend(due)
                changed = changed or bool(due)
                due = []
                if reminder.snoozed_until <= now:
                    reminder.snoozed_until = None
                    reminder.state = STATE_REMINDED
                    self._remind(reminder, reminder_time="snooze")
                    changed = True
            if due:
                reminder.fired.extend(due)
                reminder.state = STATE_REMINDED
                reminder.reminded_at = reminder.reminded_at or now
                self._remind(reminder, reminder_time=due[-1])
                changed = True
            for signal_id, when in list(reminder.deferred.items()):
                if when > now:
                    continue
                signal = next((s for s in self.rule.signals if s.id == signal_id), None)
                del reminder.deferred[signal_id]
                changed = True
                if signal and signal.enabled and reminder.state == STATE_REMINDED:
                    self._dispatch(signal, reminder)
            stage_at = self._next_stage(reminder)
            while stage_at is not None and stage_at <= now:
                reminder.stage += 1
                self._escalate(reminder)
                changed = True
                stage_at = self._next_stage(reminder)
            pending = [w for at, w in times if at not in reminder.fired]
            if stage_at is not None:
                pending.append(stage_at)
            if reminder.snoozed_until is not None:
                pending.append(reminder.snoozed_until)
            if (repeat_at := self._next_repeat(reminder)) is not None:
                if repeat_at <= now:
                    reminder.repeats += 1
                    self._remind(reminder, reminder_time="repeat")
                    changed = True
                    repeat_at = self._next_repeat(reminder)
                if repeat_at is not None:
                    pending.append(repeat_at)
            candidate = min([*pending, *reminder.deferred.values(), expire])
            next_time = candidate if next_time is None else min(next_time, candidate)
        self._schedule(next_time)
        return changed

    def _next_stage(self, reminder: Reminder) -> datetime | None:
        """When the next escalation stage of a reminding reminder starts."""
        stages = self.rule.escalation
        if reminder.state != STATE_REMINDED or reminder.stage >= len(stages):
            return None
        since = reminder.reminded_at
        if since is None:
            return None
        after = str(stages[reminder.stage]["after"])
        if ":" in after:
            tz = dt_util.get_default_time_zone()
            hour, minute = (int(part) for part in after.split(":"))
            return local_instant(since.astimezone(tz).date(), hour * 60 + minute, tz)
        return since + timedelta(minutes=duration_minutes(after))

    def _escalate(self, reminder: Reminder) -> None:
        """Send the immediate signals of a newly reached escalation stage."""
        self._fire(EVENT_REMINDED, reminder, reminder_time=f"stage_{reminder.stage}")
        for signal in self.rule.signals:
            if (
                signal.enabled
                and signal.when == WHEN_NOW
                and signal.stage == reminder.stage
            ):
                self._dispatch(signal, reminder)

    def _next_repeat(self, reminder: Reminder) -> datetime | None:
        """When an open reminder is repeated next (None: no repetition left)."""
        every = self.rule.repeat_every
        if (
            not every
            or reminder.state != STATE_REMINDED
            or reminder.repeats >= self.rule.repeat_max
        ):
            return None
        last = reminder.last_reminded or reminder.reminded_at
        return last + timedelta(minutes=every) if last else None

    def _schedule(self, when: datetime | None) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        if when is None or self._stopped:
            return

        @callback
        def _fired(_now: datetime) -> None:
            self._unsub_timer = None
            self.hass.async_create_task(self.async_process())

        self._unsub_timer = async_track_point_in_utc_time(self.hass, _fired, when)

    def _finish(self, changed: bool, *, force_update: bool = False) -> None:
        self._sync_listeners()
        if changed:
            self._on_changed()
        if changed or force_update:
            self._on_update(self)

    # ---------------------------------------------------------------- signals

    def variables(self, reminder: Reminder | Occurrence) -> dict[str, str]:
        """Text variables of a reminder as of now."""
        assignee = (
            reminder.assignee
            if isinstance(reminder, Reminder)
            else self._assign(reminder)
            if self.rule.assignee
            else None
        )
        names = {
            entity_id: state.name
            for entity_id in self.rule.sources
            if (state := self.hass.states.get(entity_id)) is not None
        }
        return build_variables(
            self.rule,
            reminder.events,
            today=dt_util.now().date(),
            tz=dt_util.get_default_time_zone(),
            language=self.hass.config.language,
            calendar_names=names,
            assignee=self.assignee_name(assignee),
        )

    def event_data(self, reminder: Reminder) -> dict[str, Any]:
        """Return the data of the bus events of a reminder."""
        return {
            "rule_id": self.rule.id,
            "rule_name": self.rule.name,
            "reminder_id": reminder.id,
            "titles": [event.summary for event in reminder.events],
            "event_start": reminder.start.isoformat(),
            "variables": self.variables(reminder),
        }

    def _fire(self, event_type: str, reminder: Reminder, **extra: Any) -> None:
        if self._on_finished and event_type in (EVENT_MISSED, EVENT_ACKNOWLEDGED):
            self._on_finished(reminder)
        self.hass.bus.async_fire(event_type, {**self.event_data(reminder), **extra})

    def _remind(self, reminder: Reminder, *, reminder_time: str | None) -> None:
        """Fire the event and send all "now" signals."""
        reminder.last_reminded = dt_util.utcnow()
        self._fire(EVENT_REMINDED, reminder, reminder_time=reminder_time)
        for signal in self.rule.signals:
            if (
                signal.enabled
                and signal.when == WHEN_NOW
                and signal.stage <= reminder.stage
            ):
                self._dispatch(signal, reminder)

    def _dispatch(
        self,
        signal: Signal,
        reminder: Reminder,
        extra: dict[str, str] | None = None,
    ) -> None:
        """Send a signal unless its limits forbid it (quiet time may defer it)."""
        now = dt_util.utcnow()
        reminder.deferred.pop(signal.id, None)
        key = (reminder.id, signal.id)
        if key in self._sending or limit_reached(signal, reminder, now):
            return
        if quiet := quiet_until(signal, now, dt_util.get_default_time_zone()):
            mode, until = quiet
            if is_deferrable(mode):
                reminder.deferred[signal.id] = until
            return
        # While it is being sent (a light signal takes seconds) the same
        # signal is not started again, so limits cannot be exceeded.
        self._sending.add(key)
        self.hass.async_create_task(self._async_send(signal, reminder, extra))

    def signal_run(
        self,
        signal: Signal,
        item: Reminder | Occurrence,
        context: Context,
        extra: dict[str, str] | None = None,
    ) -> SignalRun:
        """Build the data for sending a signal for a reminder / an event."""
        return SignalRun(
            hass=self.hass,
            rule_name=self.rule.name,
            signal=signal,
            reminder_id=item.id,
            variables={"person": "", **self.variables(item), **(extra or {})},
            plural=is_plural(self.rule, item.events),
            context=context,
            assignee=item.assignee if isinstance(item, Reminder) else None,
        )

    async def _async_send(
        self, signal: Signal, reminder: Reminder, extra: dict[str, str] | None
    ) -> None:
        try:
            if not await async_conditions_met(self.hass, signal):
                return
            reminder.signal_last[signal.id] = dt_util.utcnow()
            reminder.signals_sent[signal.id] = (
                reminder.signals_sent.get(signal.id, 0) + 1
            )
            self._on_changed()
            run = self.signal_run(signal, reminder, own_context(), extra)
            if await async_send_signal(run):
                self._fire(
                    EVENT_SIGNAL_SENT,
                    reminder,
                    signal_id=signal.id,
                    signal_type=signal.type,
                )
        finally:
            self._sending.discard((reminder.id, signal.id))

    def _clear_notifications(self, reminder: Reminder) -> None:
        if any(reminder.signals_sent.values()):
            self.hass.async_create_task(
                async_clear_notifications(
                    self.hass, self.rule.signals, reminder, Context()
                )
            )

    # ---------------------------------------------------------------- actions

    def _ackable(self, now: datetime) -> list[Reminder]:
        """Reminders a plain "done" refers to.

        All reminders that are currently reminding; if there is none, the next
        planned one when its first reminder time is near (early acknowledge).
        """
        reminded = [
            r
            for r in self.reminders.values()
            if r.state == STATE_REMINDED or r.snoozed_until is not None
        ]
        if reminded:
            return reminded
        planned = sorted(
            (r for r in self.reminders.values() if r.state == STATE_PLANNED),
            key=lambda r: r.start,
        )
        for reminder in planned:
            first = self.next_reminder_time(reminder)
            if first and first - timedelta(hours=EARLY_ACK_HOURS) <= now:
                return [reminder]
            break
        return []

    async def async_acknowledge(
        self,
        *,
        reminder_id: str | None = None,
        by: str | None = None,
        via: str | None = None,
        early: bool = True,
    ) -> list[Reminder]:
        """Mark reminders as done; returns the acknowledged ones."""
        async with self._lock:
            now = dt_util.utcnow()
            if reminder_id is not None:
                reminder = self.reminders.get(reminder_id)
                targets = [reminder] if reminder and reminder.is_open else []
            else:
                targets = self._ackable(now)
                if not early:
                    targets = [
                        r
                        for r in targets
                        if r.state == STATE_REMINDED or r.snoozed_until is not None
                    ]
            for reminder in targets:
                was_reminding = reminder.state == STATE_REMINDED
                reminder.state = STATE_DONE
                reminder.finished_at = now
                reminder.snoozed_until = None
                reminder.deferred.clear()
                reminder.acknowledged_by = by
                reminder.acknowledged_via = via
                self._fire(
                    EVENT_ACKNOWLEDGED,
                    reminder,
                    acknowledged_by=by,
                    acknowledged_via=via,
                )
                if was_reminding:
                    self._clear_notifications(reminder)
                self._run_on_done(reminder, by, via)
            if targets:
                self._process(now)  # re-plan the timer
        self._finish(bool(targets))
        if targets and self.rule.interval:
            # The next due day depends on this acknowledgement.
            self.hass.async_create_task(self.async_refresh())
        return targets

    def _run_on_done(self, reminder: Reminder, by: str | None, via: str | None) -> None:
        if self._on_done is None:
            return
        variables = {
            **self.variables(reminder),
            "reminder_id": reminder.id,
            "person": by or "",
            "via": via or "",
            "titles": [event.summary for event in reminder.events],
        }
        self.hass.async_create_task(
            self._on_done.async_run(run_variables=variables, context=Context())
        )

    async def async_snooze(
        self, minutes: int, *, reminder_id: str | None = None
    ) -> list[Reminder]:
        """Remind again later: reminding -> planned until the time is over."""
        async with self._lock:
            now = dt_util.utcnow()
            targets = [
                r
                for r in self.open_reminders
                if reminder_id is None or r.id == reminder_id
            ]
            for reminder in targets:
                reminder.state = STATE_PLANNED
                reminder.snoozed_until = now + timedelta(minutes=minutes)
                reminder.deferred.clear()
                self._clear_notifications(reminder)
            if targets:
                self._process(now)
        self._finish(bool(targets))
        return targets

    async def async_trigger(self) -> Reminder | None:
        """Remind now for the open or the next planned reminder."""
        async with self._lock:
            now = dt_util.utcnow()
            candidates = sorted(
                (r for r in self.reminders.values() if r.is_open),
                key=lambda r: (r.state != STATE_REMINDED, r.start),
            )
            reminder = candidates[0] if candidates else None
            if reminder is not None:
                reminder.snoozed_until = None
                reminder.state = STATE_REMINDED
                reminder.reminded_at = reminder.reminded_at or now
                self._remind(reminder, reminder_time=None)
        self._finish(reminder is not None)
        return reminder

    # ----------------------------------------------------------------- status

    def current(self, now: datetime | None = None) -> Reminder | None:
        """Return the reminder the rule's state refers to.

        A reminding one first; else the most recently finished one while its
        event is not over (at least until the end of that day); else the next
        planned one.
        """
        now = now or dt_util.utcnow()
        tz = dt_util.get_default_time_zone()
        reminders = sorted(self.reminders.values(), key=lambda r: r.start)
        if reminded := [r for r in reminders if r.state == STATE_REMINDED]:
            return reminded[0]
        finished = []
        for reminder in reminders:
            if reminder.is_open or reminder.finished_at is None:
                continue
            day_end = local_instant(
                reminder.finished_at.astimezone(tz).date() + timedelta(days=1), 0, tz
            )
            if now < max(day_end, reminder.end):
                finished.append(reminder)
        if finished:
            return max(finished, key=lambda r: r.finished_at or r.start)
        planned = [r for r in reminders if r.state == STATE_PLANNED]
        return planned[0] if planned else None

    @property
    def state(self) -> str:
        """State of the rule: planned / reminded / done / missed / inactive."""
        current = self.current()
        return current.state if current else STATE_INACTIVE

    @property
    def open_reminders(self) -> list[Reminder]:
        """Reminders that are reminding right now."""
        return sorted(
            (r for r in self.reminders.values() if r.state == STATE_REMINDED),
            key=lambda r: r.start,
        )

    def next_occurrence(self, now: datetime | None = None) -> Occurrence | None:
        """Next matching event (bundle) that still needs something to be done.

        Skipped: events that are over, whose reminder is done or missed, or
        whose expiry has passed. To-dos and intervals stay due until they are
        acknowledged (they are carried to today while overdue), so for them
        only "done" counts.
        """
        now = now or dt_util.utcnow()
        for occurrence in self.upcoming:
            if occurrence.end <= now:
                continue
            reminder = self.reminders.get(occurrence.id)
            if self._stays_due(occurrence):
                if reminder is not None and reminder.state == STATE_DONE:
                    continue
                return occurrence
            if reminder is not None and reminder.state in (STATE_DONE, STATE_MISSED):
                continue
            if self.expire_at(occurrence) <= now:
                continue
            return occurrence
        return None

    @staticmethod
    def _stays_due(occurrence: Occurrence) -> bool:
        """Whether an occurrence comes from to-dos / an interval only."""
        return all(
            event.calendar.split(".", 1)[0] in (TODO_DOMAIN, INTERVAL_SOURCE)
            for event in occurrence.events
        )
