"""Repair flow for a Starlink session that the account API no longer accepts.

The coordinator raises a fixable repair issue after a minute of 401 responses.
Home Assistant then lists it under Settings > System > Repairs with a Fix
button that opens this flow, so the user can paste a fresh browser cookie where
the problem is reported. Before this, the integration only left a persistent
notification behind, which could not do anything about the problem.

The issue is deleted automatically by Home Assistant when the flow finishes with
``async_create_entry``; the coordinator also deletes it as soon as the account
API accepts the session again.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .config_flow import COOKIE_SCHEMA, async_store_cookie, async_validate_cookie
from .const import CONF_COOKIE


class StarlinkSessionExpiredRepairFlow(RepairsFlow):
    """Ask for a fresh browser cookie and store it on the affected entry."""

    def __init__(self, data: dict[str, Any]) -> None:
        """Initialize the repair flow with the issue's data."""
        self._entry_id: str | None = data.get("entry_id")

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Validate the pasted cookie, store it and reload the entry."""
        entry = (
            self.hass.config_entries.async_get_entry(self._entry_id)
            if self._entry_id
            else None
        )
        if entry is None:
            # The entry was removed while the repair was pending: nothing left
            # to repair, and leaving the flow open would only confuse.
            return self.async_abort(reason="entry_not_found")

        if user_input is not None:
            cookie = user_input[CONF_COOKIE].strip()
            error = await async_validate_cookie(self.hass, cookie)
            if error is None:
                await async_store_cookie(self.hass, entry, cookie)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_create_entry(data={})
            return self.async_show_form(
                step_id="init", data_schema=COOKIE_SCHEMA, errors={"base": error}
            )

        return self.async_show_form(step_id="init", data_schema=COOKIE_SCHEMA)


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, str] | None
) -> RepairsFlow:
    """Create the flow that fixes a Starlink Remote issue."""
    return StarlinkSessionExpiredRepairFlow(data or {})
