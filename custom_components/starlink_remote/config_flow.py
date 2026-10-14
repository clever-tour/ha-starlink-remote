"""Config, options and re-authentication flow for Starlink Remote."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import storage
from .const import CONF_COOKIE, DOMAIN
from .session import account_number_from_cookie
from .validation import (
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    validate_cookie,
)

_LOGGER = logging.getLogger(__name__)

#: The cookie is a credential: the selector masks it while typing, so it never
#: sits in plain sight in the browser window (or in a screenshot of it).
_COOKIE_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

COOKIE_SCHEMA = vol.Schema({vol.Required(CONF_COOKIE): _COOKIE_SELECTOR})

#: Options form: empty means "keep the cookie that is already stored", which is
#: why the stored value is not prefilled into the form.
OPTIONS_SCHEMA = vol.Schema({vol.Optional(CONF_COOKIE, default=""): _COOKIE_SELECTOR})


def _looks_like_cookie(raw: str) -> bool:
    """Return True when the input can be a browser cookie string.

    A deliberate cheap check, run before the credential is sent anywhere: it
    only catches the obvious mistakes (an empty field, a pasted URL).
    """
    return "=" in raw and not raw.startswith("http")


async def async_validate_cookie(hass: HomeAssistant, cookie: str) -> str | None:
    """Return an error key when the pasted cookie is not usable.

    The check is one authenticated account-API call (see ``validation.py``), so
    it runs in an executor and its result is the only thing that unlocks the
    "success" answer of a flow.
    """
    return await hass.async_add_executor_job(validate_cookie, cookie)


def _update_is_live(hass: HomeAssistant, entry_id: str) -> bool:
    """Return True when the entry is running and its first poll succeeded.

    A reload awaits the coordinator's first refresh, so after
    ``async_reload()`` this reflects the data update with the new cookie: a
    session that only *looks* valid fails here.
    """
    coordinator = hass.data.get(DOMAIN, {}).get(entry_id)
    return coordinator is not None and coordinator.last_update_success


class StarlinkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration and re-authentication."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle initial configuration."""
        if user_input is not None:
            cookie = user_input[CONF_COOKIE].strip()
            if not _looks_like_cookie(cookie):
                return self.async_show_form(
                    step_id="user",
                    data_schema=COOKIE_SCHEMA,
                    errors={"base": ERROR_INVALID_AUTH},
                )

            if error := await async_validate_cookie(self.hass, cookie):
                # No entry is created for a credential that does not work: the
                # old code answered "success" and left the user with an entry
                # whose account API answered 401 on every poll.
                return self.async_show_form(
                    step_id="user",
                    data_schema=COOKIE_SCHEMA,
                    errors={"base": error},
                )

            await async_save_cookie(self.hass, cookie)

            # One entry per Starlink account: the account number is part of the
            # cookie, so a second attempt for the same account is a duplicate
            # rather than a second integration. (Older entries were created
            # without a unique id, so this only applies to new ones.)
            if account := account_number_from_cookie(cookie):
                await self.async_set_unique_id(account)
                self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title="Starlink Remote", data={CONF_COOKIE: cookie}
            )

        return self.async_show_form(step_id="user", data_schema=COOKIE_SCHEMA)

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle re-authentication when the cookie expired."""
        return await self.async_step_reauth_confirm(user_input)

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm re-authentication and replace the stored cookie."""
        if user_input is not None:
            cookie = user_input[CONF_COOKIE].strip()
            if not _looks_like_cookie(cookie):
                return self.async_show_form(
                    step_id="reauth_confirm",
                    data_schema=COOKIE_SCHEMA,
                    errors={"base": ERROR_INVALID_AUTH},
                )

            error = await async_validate_cookie(self.hass, cookie)
            if error:
                return self.async_show_form(
                    step_id="reauth_confirm",
                    data_schema=COOKIE_SCHEMA,
                    errors={"base": error},
                )

            entry = self._get_reauth_entry()

            previous = entry.data.get(CONF_COOKIE, "")
            await async_store_cookie(self.hass, entry, cookie)
            await self.hass.config_entries.async_reload(entry.entry_id)
            if not _update_is_live(self.hass, entry.entry_id):
                # The cookie passed the API check but the entry still does not
                # come up: reinstate the old credential and report the failure
                # rather than aborting with "reauth_successful".
                await async_store_cookie(self.hass, entry, previous)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_show_form(
                    step_id="reauth_confirm",
                    data_schema=COOKIE_SCHEMA,
                    errors={"base": ERROR_CANNOT_CONNECT},
                )

            return self.async_abort(reason="reauth_successful")

        return self.async_show_form(step_id="reauth_confirm", data_schema=COOKIE_SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow for this handler.

        The handler takes no arguments: Home Assistant passes ``config_entry``
        to the options flow itself and ``OptionsFlow.config_entry`` is a
        read-only property, so assigning to it raises an AttributeError.
        """
        return StarlinkOptionsFlowHandler()


class StarlinkOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle the options flow: replacing an expired cookie."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Update the stored browser cookie."""
        if user_input is not None:
            cookie = (user_input.get(CONF_COOKIE) or "").strip()
            if not cookie:
                # Nothing typed: keep the current session, just close the dialog.
                _LOGGER.debug("Options submitted without a new cookie, keeping the current one")
                return self.async_create_entry(title="", data={})

            if not _looks_like_cookie(cookie):
                return self.async_show_form(
                    step_id="init",
                    data_schema=OPTIONS_SCHEMA,
                    errors={"base": ERROR_INVALID_AUTH},
                )

            error = await async_validate_cookie(self.hass, cookie)
            if error:
                # Report the failure in the dialog instead of closing it with a
                # success message for a cookie the account API just refused.
                return self.async_show_form(
                    step_id="init",
                    data_schema=OPTIONS_SCHEMA,
                    errors={"base": error},
                )

            entry = self.config_entry
            previous = entry.data.get(CONF_COOKIE, "")
            await async_store_cookie(self.hass, entry, cookie)

            # The coordinator keeps the httpx client it built with the OLD
            # cookie, so the entry has to be reloaded for the new one to be used
            # (this also rebuilds every entity's connection state).
            await self.hass.config_entries.async_reload(entry.entry_id)
            if not _update_is_live(self.hass, entry.entry_id):
                await async_store_cookie(self.hass, entry, previous)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_show_form(
                    step_id="init",
                    data_schema=OPTIONS_SCHEMA,
                    errors={"base": ERROR_CANNOT_CONNECT},
                )

            _LOGGER.info("Stored a new cookie; the entry reloaded with a successful poll")
            return self.async_create_entry(title="", data={CONF_COOKIE: cookie})

        return self.async_show_form(step_id="init", data_schema=OPTIONS_SCHEMA)


async def async_store_cookie(
    hass: HomeAssistant, entry: config_entries.ConfigEntry, cookie: str
) -> None:
    """Store ``cookie`` in the entry and mirror it to the storage file.

    The entry is the source of truth for the cookie; the storage file is only a
    mirror that the coordinator reads when it builds its HTTP client. An empty
    cookie removes the file rather than writing an empty credential.
    """
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_COOKIE: cookie}
    )
    await hass.async_add_executor_job(storage.save_cookie, hass, cookie)


async def async_save_cookie(hass: HomeAssistant, cookie: str) -> None:
    """Mirror the cookie to the storage file (disk I/O runs in an executor)."""
    await hass.async_add_executor_job(storage.save_cookie, hass, cookie)
