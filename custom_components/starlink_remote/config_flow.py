from __future__ import annotations
import logging, os
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from .const import CONF_COOKIE, DOMAIN, CONF_COOKIE_FILE

_LOGGER = logging.getLogger(__name__)

class StarlinkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def _save_cookie_to_disk(self, cookie: str):
        """Mirror the cookie to the persistent storage file."""
        persist_dir = self.hass.config.path('.storage', 'starlink-remote-cookie-storage')
        cookie_path = os.path.join(persist_dir, CONF_COOKIE_FILE)
        try:
            os.makedirs(persist_dir, exist_ok=True)
            with open(cookie_path, 'w') as f:
                f.write(cookie)
            _LOGGER.debug("Saved cookie to persistent storage: %s", cookie_path)
        except Exception as e:
            _LOGGER.error("Failed to save cookie to disk: %s", e)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle initial configuration."""
        errors = {}
        if user_input is not None:
            await self.hass.async_add_executor_job(
                self._save_cookie_to_disk, user_input[CONF_COOKIE]
            )

            return self.async_create_entry(
                title="Starlink Remote",
                data={CONF_COOKIE: user_input[CONF_COOKIE]}
            )

        return self.async_show_form(
            step_id='user',
            data_schema=vol.Schema({vol.Required(CONF_COOKIE): str}),
            errors=errors
        )

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle re-authentication when cookie expires."""
        return await self.async_step_reauth_confirm(user_input)

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Confirm re-authentication and update the cookie."""
        errors = {}
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
            self.hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_COOKIE: user_input[CONF_COOKIE]}
            )
            await self.hass.async_add_executor_job(
                self._save_cookie_to_disk, user_input[CONF_COOKIE]
            )
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_COOKIE): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> StarlinkOptionsFlowHandler:
        """Get the options flow for this handler."""
        return StarlinkOptionsFlowHandler(config_entry)

class StarlinkOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Starlink Remote."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    def _save_cookie_to_disk(self, cookie: str):
        """Mirror the cookie to the persistent storage file."""
        persist_dir = self.hass.config.path('.storage', 'starlink-remote-cookie-storage')
        cookie_path = os.path.join(persist_dir, CONF_COOKIE_FILE)
        try:
            os.makedirs(persist_dir, exist_ok=True)
            with open(cookie_path, 'w') as f:
                f.write(cookie)
        except Exception as e:
            _LOGGER.error("Failed to save cookie to disk: %s", e)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Update the main config entry data as well
            new_data = {**self.config_entry.data, CONF_COOKIE: user_input[CONF_COOKIE]}
            self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
            
            # Mirror to disk
            await self.hass.async_add_executor_job(
                self._save_cookie_to_disk, user_input[CONF_COOKIE]
            )
            
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_COOKIE, 
                    default=self.config_entry.data.get(CONF_COOKIE)
                ): str,
            }),
        )
