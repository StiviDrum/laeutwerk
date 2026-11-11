"""Send the signals of a rule (0.1: push notifications)."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .compat import vol
from .const import ACTION_ACK_PREFIX, NOTIFICATION_TAG_PREFIX
from .matching import render
from .model import SIGNAL_NOTIFY, Reminder, Signal

_LOGGER = logging.getLogger(__name__)

MOBILE_APP_PREFIX = "notify.mobile_app_"
CLEAR_NOTIFICATION = "clear_notification"


def notification_tag(reminder_id: str) -> str:
    """Tag that lets a later notification replace or clear this one."""
    return f"{NOTIFICATION_TAG_PREFIX}{reminder_id}"


def notify_payload(
    signal: Signal, reminder: Reminder, variables: Mapping[str, str], plural: bool
) -> dict[str, Any]:
    """Service data for a notify action (title, message, buttons)."""
    config = signal.config

    def text(key: str) -> str:
        template = (plural and config.get(f"{key}_plural")) or config.get(key)
        return render(template, variables)

    data: dict[str, Any] = {
        **config.get("data", {}),
        "tag": notification_tag(reminder.id),
    }
    if actions := config.get("actions"):
        data["actions"] = [
            {"action": f"{ACTION_ACK_PREFIX}{reminder.id}", "title": action["label"]}
            for action in actions
            if action.get("ack")
        ]
    payload: dict[str, Any] = {"message": text("message"), "data": data}
    if title := text("title"):
        payload["title"] = title
    return payload


async def _async_notify(
    hass: HomeAssistant, target: str, payload: dict[str, Any], context: Context
) -> bool:
    domain, _, service = target.partition(".")
    if not hass.services.has_service(domain, service):
        _LOGGER.warning("Notify action %s does not exist", target)
        return False
    try:
        await hass.services.async_call(
            domain, service, payload, blocking=True, context=context
        )
    except (HomeAssistantError, vol.Invalid) as err:
        _LOGGER.warning("Notify action %s failed: %s", target, err)
        return False
    return True


async def async_send_signal(
    hass: HomeAssistant,
    signal: Signal,
    reminder: Reminder,
    *,
    variables: Mapping[str, str],
    plural: bool,
    context: Context,
) -> bool:
    """Send one signal; True if at least one target was reached."""
    if signal.type != SIGNAL_NOTIFY:
        return False
    payload = notify_payload(signal, reminder, variables, plural)
    sent = False
    for target in signal.config.get("targets", []):
        sent = await _async_notify(hass, target, payload, context) or sent
    return sent


async def async_clear_notifications(
    hass: HomeAssistant, signals: list[Signal], reminder: Reminder, context: Context
) -> None:
    """Remove the push notifications of a reminder from the phones."""
    payload = {
        "message": CLEAR_NOTIFICATION,
        "data": {"tag": notification_tag(reminder.id)},
    }
    for signal in signals:
        if signal.type != SIGNAL_NOTIFY or not reminder.signals_sent.get(signal.id):
            continue
        for target in signal.config.get("targets", []):
            if target.startswith(MOBILE_APP_PREFIX):
                await _async_notify(hass, target, payload, context)
