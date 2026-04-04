from __future__ import annotations
import logging
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from .const import CONF_COOKIE, DOMAIN

_LOGGER = logging.getLogger(__name__)

class StarlinkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            # We just save the cookie and create the entry.
            # Hardware discovery will happen in the coordinator.
            return self.async_create_entry(
                title="Starlink Remote",
                data={CONF_COOKIE: user_input[CONF_COOKIE]}
            )

        return self.async_show_form(
            step_id='user',
            data_schema=vol.Schema({vol.Required(CONF_COOKIE): str}),
            errors=errors
        )
