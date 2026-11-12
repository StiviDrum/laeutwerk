"""Constants for the Läutwerk integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "laeutwerk"
NAME: Final = "Läutwerk"

STORAGE_KEY: Final = "laeutwerk"
STORAGE_VERSION: Final = 1
STORAGE_MINOR_VERSION: Final = 3

# Finished reminders kept per rule (history in the card and diagnostics).
HISTORY_MAX: Final = 50

CARD_FILENAME: Final = "laeutwerk-card.js"
CARD_URL_BASE: Final = "/laeutwerk_static"

SIGNAL_RULE_STATUS: Final = "laeutwerk_rule_status_{}"

EVENT_REMINDED: Final = "laeutwerk_reminded"
EVENT_SIGNAL_SENT: Final = "laeutwerk_signal_sent"
EVENT_ACKNOWLEDGED: Final = "laeutwerk_acknowledged"
EVENT_MISSED: Final = "laeutwerk_missed"

# Calendar look-ahead and refresh interval (SPEC 0.1).
LOOKAHEAD_DAYS: Final = 14
REFRESH_MINUTES: Final = 15

EARLY_OFF: Final = "off"
EARLY_HOURS: Final = "hours"
EARLY_ALWAYS: Final = "always"

# Mobile app notification action: LAEUTWERK_ACK__<reminder id>
ACTION_ACK_PREFIX: Final = "LAEUTWERK_ACK__"
NOTIFICATION_TAG_PREFIX: Final = "laeutwerk_"

# Mobile app notification action: LAEUTWERK_SNOOZE__<minutes>__<reminder id>
ACTION_SNOOZE_PREFIX: Final = "LAEUTWERK_SNOOZE__"

EVENT_TAG_SCANNED: Final = "tag_scanned"

ACK_VIA_TAG: Final = "tag"
ACK_VIA_TRIGGER: Final = "trigger"
ACK_VIA_BUTTON: Final = "button"
ACK_VIA_SERVICE: Final = "service"
ACK_VIA_NOTIFICATION: Final = "notify_action"
