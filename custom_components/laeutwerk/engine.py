"""Runtime of one rule: find events, keep reminders, fire signals once."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
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
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.util import dt as dt_util

from .const import (
    EARLY_ACK_HOURS,
    EVENT_ACKNOWLEDGED,
    EVENT_MISSED,
    EVENT_REMINDED,
    EVENT_SIGNAL_SENT,
    LOOKAHEAD_DAYS,
)
from .matching import Occurrence, build_occurrences, build_variables, is_plural
from .model import (
    STATE_DONE,
    STATE_INACTIVE,
    STATE_MISSED,
    STATE_PLANNED,
    STATE_REMINDED,
    WHEN_NOW,
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
from .sources import async_fetch_events
from .timespec import local_instant, parse_timespec, resolve

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
    ) -> None:
        """Initialise; ``reminders`` is the persisted dict owned by the manager."""
        self.hass = hass
        self.rule = rule
        self.reminders = reminders
        self.upcoming: list[Occurrence] = []
        self.errors: dict[str, str] = {}
        self._on_update = on_update
        self._on_changed = on_changed
        self._lock = asyncio.Lock()
        self._unsub_timer: CALLBACK_TYPE | None = None
        self._unsub_sources: CALLBACK_TYPE | None = None
        self._unsub_debounce: CALLBACK_TYPE | None = None
        self._stopped = False
        self._sending: set[tuple[str, str]] = set()

    # ------------------------------------------------------------ lifecycle

    async def async_start(self) -> None:
        """Start listening to the source calendars and read them once."""
        self._unsub_sources = async_track_state_change_event(
            self.hass, self.rule.sources, self._async_source_changed
        )
        await self.async_refresh()

    async def async_stop(self) -> None:
        """Cancel timers and listeners."""
        self._stopped = True
        for attr in ("_unsub_timer", "_unsub_sources", "_unsub_debounce"):
            if unsub := getattr(self, attr):
                unsub()
                setattr(self, attr, None)

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
            occurrences = sorted(
                build_occurrences(self.rule, events), key=lambda o: o.start
            )
            self.upcoming = occurrences
            changed = self._reconcile(occurrences, now, today, complete=not errors)
            changed = self._process(now) or changed
        self._finish(changed, force_update=True)

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
            if reminder.state == STATE_PLANNED or (
                reminder.state == STATE_REMINDED and reminder.day >= today
            ):
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
            pending = [w for at, w in times if at not in reminder.fired]
            candidate = min([*pending, *reminder.deferred.values(), expire])
            next_time = candidate if next_time is None else min(next_time, candidate)
        self._schedule(next_time)
        return changed

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
        if changed:
            self._on_changed()
        if changed or force_update:
            self._on_update(self)

    # ---------------------------------------------------------------- signals

    def variables(self, reminder: Reminder | Occurrence) -> dict[str, str]:
        """Text variables of a reminder as of now."""
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
        self.hass.bus.async_fire(event_type, {**self.event_data(reminder), **extra})

    def _remind(self, reminder: Reminder, *, reminder_time: str | None) -> None:
        """Fire the event and send all "now" signals."""
        self._fire(EVENT_REMINDED, reminder, reminder_time=reminder_time)
        for signal in self.rule.signals:
            if signal.enabled and signal.when == WHEN_NOW:
                self._dispatch(signal, reminder)

    def _dispatch(self, signal: Signal, reminder: Reminder) -> None:
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
        self.hass.async_create_task(self._async_send(signal, reminder))

    def signal_run(
        self, signal: Signal, item: Reminder | Occurrence, context: Context
    ) -> SignalRun:
        """Build the data for sending a signal for a reminder / an event."""
        return SignalRun(
            hass=self.hass,
            rule_name=self.rule.name,
            signal=signal,
            reminder_id=item.id,
            variables=self.variables(item),
            plural=is_plural(self.rule, item.events),
            context=context,
        )

    async def _async_send(self, signal: Signal, reminder: Reminder) -> None:
        try:
            if not await async_conditions_met(self.hass, signal):
                return
            reminder.signal_last[signal.id] = dt_util.utcnow()
            reminder.signals_sent[signal.id] = (
                reminder.signals_sent.get(signal.id, 0) + 1
            )
            self._on_changed()
            run = self.signal_run(signal, reminder, Context())
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
        reminded = [r for r in self.reminders.values() if r.state == STATE_REMINDED]
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
                    targets = [r for r in targets if r.state == STATE_REMINDED]
            for reminder in targets:
                reminder.state = STATE_DONE
                reminder.finished_at = now
                reminder.deferred.clear()
                reminder.acknowledged_by = by
                reminder.acknowledged_via = via
                self._fire(
                    EVENT_ACKNOWLEDGED,
                    reminder,
                    acknowledged_by=by,
                    acknowledged_via=via,
                )
                self._clear_notifications(reminder)
            if targets:
                self._process(now)  # re-plan the timer
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
        """Next matching event (bundle) that is not over yet."""
        now = now or dt_util.utcnow()
        return next((o for o in self.upcoming if o.end > now), None)
