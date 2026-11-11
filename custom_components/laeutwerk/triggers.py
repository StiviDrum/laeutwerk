"""Home Assistant triggers for opportunities and acknowledgements."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Coroutine
import logging
from typing import Any

from homeassistant.core import CALLBACK_TYPE, Context, HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, trigger as trigger_helper

from .compat import vol
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

TriggerAction = Callable[[dict[str, Any], Context | None], Coroutine[Any, Any, None]]

# Contexts of our own actions (light signals switch lamps): the resulting
# state changes are no opportunities and no manual operation.
_OWN_CONTEXTS: deque[str] = deque(maxlen=200)


def own_context() -> Context:
    """Create a context that is recognised as caused by Läutwerk."""
    context = Context()
    _OWN_CONTEXTS.append(context.id)
    return context


def is_own_context(context: Context | None) -> bool:
    """Whether something was caused by a Läutwerk signal."""
    return context is not None and (
        context.id in _OWN_CONTEXTS or context.parent_id in _OWN_CONTEXTS
    )


def is_manual(context: Context | None) -> bool:
    """Whether a change was a real operation, not an automation or script.

    Automations and scripts act with a context that has a parent; a wall
    switch, the app or the dashboard do not.
    """
    return context is None or (
        context.parent_id is None and not is_own_context(context)
    )


def as_trigger_list(value: Any) -> list[dict[str, Any]]:
    """Check trigger configuration but keep it as given (for the editor)."""
    triggers = cv.ensure_list(value)
    if not triggers:
        raise vol.Invalid("at least one trigger is required")
    cv.TRIGGER_SCHEMA(triggers)
    return triggers


async def async_validate_triggers(hass: HomeAssistant, value: Any) -> None:
    """Validate triggers against the running Home Assistant."""
    await trigger_helper.async_validate_trigger_config(
        hass, cv.TRIGGER_SCHEMA(cv.ensure_list(value))
    )


def trigger_state(variables: dict[str, Any]) -> State | None:
    """State object that caused a trigger, if it has one."""
    state = (variables.get("trigger") or {}).get("to_state")
    return state if isinstance(state, State) else None


def person_of(
    hass: HomeAssistant, variables: dict[str, Any], context: Context | None
) -> str:
    """Who caused a trigger: the person that changed, else the acting user."""
    state = trigger_state(variables)
    if state is not None and state.domain == "person":
        return state.name
    if state is not None and state.domain == "device_tracker":
        for person in hass.states.async_all("person"):
            if state.entity_id in person.attributes.get("device_trackers", []):
                return person.name
    user_id = context.user_id if context else None
    if user_id is None and state is not None:
        user_id = state.context.user_id
    if user_id:
        for person in hass.states.async_all("person"):
            if person.attributes.get("user_id") == user_id:
                return person.name
    return ""


class TriggerListener:
    """A list of triggers with one callback, active only while wanted."""

    def __init__(
        self, hass: HomeAssistant, name: str, config: Any, action: TriggerAction
    ) -> None:
        """Initialise (not listening yet)."""
        self.hass = hass
        self.name = name
        self.config = config
        self._action = action
        self._unsub: CALLBACK_TYPE | None = None
        self._attaching = False
        self._wanted = False

    @property
    def active(self) -> bool:
        """Whether the triggers are (being) attached."""
        return self._unsub is not None or self._attaching

    def update(self, wanted: bool) -> None:
        """Start or stop listening."""
        self._wanted = wanted
        if wanted and not self.active:
            self._attaching = True
            self.hass.async_create_task(self._async_attach())
        elif not wanted and self._unsub:
            self._unsub()
            self._unsub = None

    async def _async_attach(self) -> None:
        unsub: CALLBACK_TYPE | None = None
        try:
            config = await trigger_helper.async_validate_trigger_config(
                self.hass, cv.TRIGGER_SCHEMA(cv.ensure_list(self.config))
            )
            unsub = await trigger_helper.async_initialize_triggers(
                self.hass, config, self._action, DOMAIN, self.name, self._log
            )
        except (vol.Invalid, HomeAssistantError) as err:
            _LOGGER.warning("%s: cannot set up trigger: %s", self.name, err)
        finally:
            self._attaching = False
        if unsub and not self._wanted:
            unsub()
        else:
            self._unsub = unsub

    def _log(self, level: int, msg: str, **kwargs: Any) -> None:
        _LOGGER.log(level, "%s %s", self.name, msg, **kwargs)
