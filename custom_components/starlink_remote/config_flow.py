from __future__ import annotations
import logging, os
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
            # Ensure the storage directory exists when the user enters the data
            persist_dir = self.hass.config.path('.storage', 'starlink-remote-cookie-storage')
            try:
                await self.hass.async_add_executor_job(os.makedirs, persist_dir, 0o755, True)
            except Exception as e:
                _LOGGER.error("Failed to create storage directory %s: %s", persist_dir, e)

            return self.async_create_entry(
                title="Starlink Remote",
                data={CONF_COOKIE: user_input[CONF_COOKIE]}
            )

        return self.async_show_form(
            step_id='user',
            data_schema=vol.Schema({vol.Required(CONF_COOKIE): str}),
            errors=errors
        )
