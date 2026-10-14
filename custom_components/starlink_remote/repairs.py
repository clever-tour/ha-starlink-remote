"""Repair flow for a Starlink session that the account API no longer accepts.

The coordinator raises a fixable repair issue after a minute of rejected
requests. Home Assistant then lists it under Settings > System > Repairs with a
Fix button that opens this flow, so the user can paste a fresh browser cookie
where the problem is reported.

The flow runs the same check and shows the same connection log as the config
and options dialogs, so all three agree on what a cookie has to answer before
it is stored; the reload phase makes sure the entry actually comes back up with
the new credential before the flow reports success. Home Assistant deletes the
issue when the flow finishes with ``async_create_entry``; the coordinator also
deletes it, together with the notification that came with it, as soon as the
account API accepts a session again.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .config_flow import (
    CONFIRM_SCHEMA,
    COOKIE_SCHEMA,
    CookieConnectFlow,
    async_store_and_reload,
    looks_like_cookie,
)
from .const import CONF_COOKIE
from .validation import ERROR_INVALID_AUTH


class StarlinkSessionExpiredRepairFlow(CookieConnectFlow, RepairsFlow):
    """Ask for a fresh browser cookie and store it on the affected entry."""

    _cookie_schema = COOKIE_SCHEMA

    def __init__(self, data: dict[str, Any]) -> None:
        """Initialize the repair flow with the issue's data."""
        self._entry_id: str | None = data.get("entry_id")

    # -- the affected entry ------------------------------------------------

    def _resolve_entry(self) -> ConfigEntry | None:
        """Return the entry this repair belongs to, when it still exists."""
        if not self._entry_id:
            return None
        return self.hass.config_entries.async_get_entry(self._entry_id)

    # -- steps -------------------------------------------------------------

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the cookie dialog when the core enters the flow on ``init``."""
        return await self._async_cookie_step("init", user_input)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the cookie dialog when the core enters the flow on ``user``.

        Cores from 2026.x enter repair flows on the ``user`` step, the same way
        they do for config and options flows; older cores used ``init``. Both
        names run the same dialog and the form reports the step it was entered
        on, so the translated title always matches.
        """
        return await self._async_cookie_step("user", user_input)

    async def _async_cookie_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> FlowResult:
        """Show the cookie form, or test a submitted cookie phase by phase."""
        self._connect_entry_step = step_id
        if self._resolve_entry() is None:
            # The entry was removed while the repair was pending: nothing left
            # to repair, and leaving the flow open would only confuse.
            return self.async_abort(reason="entry_not_found")

        if user_input is not None:
            cookie = user_input[CONF_COOKIE].strip()
            if not looks_like_cookie(cookie):
                return self._async_cookie_form(
                    step_id=step_id, errors={"base": ERROR_INVALID_AUTH}
                )
            return self._async_start_connect(
                cookie,
                entry_step=step_id,
                progress_title="Testing the new cookie",
                log_title="Starlink connection check",
            )

        return self._async_cookie_form(step_id=step_id)

    # -- phases ------------------------------------------------------------

    def _extra_phases(self) -> tuple[str, ...]:
        """The repair runs inside an existing entry, so it also reloads it."""
        return ("reload",)

    async def _async_phase_reload(self) -> None:
        """Store the cookie, reload the entry and check the first poll."""
        entry = self._resolve_entry()
        probe = self._probe
        assert entry is not None and probe is not None
        await async_store_and_reload(self.hass, entry, self._connect_cookie, probe)
        self.async_update_progress(len(probe.results) / len(probe.phases))

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the log of the successful check and close the repair."""
        if user_input is None:
            return self.async_show_form(
                step_id="confirm",
                data_schema=CONFIRM_SCHEMA,
                description_placeholders={
                    "log": self._log(
                        footer=(
                            "Submit to close the repair and keep the new session."
                        )
                    )
                },
            )
        return self.async_create_entry(data={})


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, str] | None
) -> RepairsFlow:
    """Create the flow that fixes a Starlink Remote issue."""
    return StarlinkSessionExpiredRepairFlow(data or {})
