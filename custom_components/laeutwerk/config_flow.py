"""Config flow for Läutwerk (single instance) with the household quiet time."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .compat import vol
from .const import DOMAIN, NAME
from .model import QUIET_DEFER, QUIET_SKIP

_TIME = selector.TimeSelector()


def _hhmm(value: str) -> str:
    return value[:5]


class LaeutwerkOptionsFlow(OptionsFlow):
    """One quiet window for the whole household."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the household quiet time."""
        errors: dict[str, str] = {}
        if user_input is not None:
            start, end = user_input.get("from"), user_input.get("to")
            if bool(start) != bool(end):
                errors["base"] = "incomplete"
            else:
                quiet = (
                    [
                        {
                            "from": _hhmm(start),
                            "to": _hhmm(end),
                            "mode": user_input.get("mode", QUIET_SKIP),
                        }
                    ]
                    if start
                    else []
                )
                return self.async_create_entry(data={"quiet": quiet})
        current = (self.config_entry.options.get("quiet") or [{}])[0]
        schema = vol.Schema(
            {
                vol.Optional("from"): _TIME,
                vol.Optional("to"): _TIME,
                vol.Required("mode", default=QUIET_SKIP): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[QUIET_SKIP, QUIET_DEFER],
                        translation_key="quiet_mode",
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or current
            ),
            errors=errors,
        )


class LaeutwerkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Läutwerk config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> LaeutwerkOptionsFlow:
        """Return the options flow."""
        return LaeutwerkOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm and create the single Zeitwerk entry."""
        if user_input is not None:
            return self.async_create_entry(title=NAME, data={})
        return self.async_show_form(step_id="user")
