"""Set up the Starlink Remote integration and clean up after it."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from . import storage
from .const import CONF_COOKIE, DOMAIN, ISSUE_SESSION_EXPIRED
from .coordinator import StarlinkCoordinator
from .session import account_number_from_cookie

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an old config entry.

    Version 1 entries were created before the config flow used the account
    number as the unique id, so a second flow for the same account could still
    create a duplicate entry. Migration derives the unique id from the stored
    cookie and moves the entry to version 2.
    """
    if entry.version > 2:
        # Downgrading is not supported.
        return False

    if entry.version == 1:
        account_number = account_number_from_cookie(entry.data.get(CONF_COOKIE, ""))
        if account_number:
            hass.config_entries.async_update_entry(
                entry, unique_id=account_number, version=2
            )
        else:
            # Cannot derive the unique id from this cookie; leave the entry as
            # it is rather than moving it to a version it does not match.
            return True

    _LOGGER.debug("Migrated Starlink Remote entry %s to version %s", entry.entry_id, entry.version)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Starlink Remote from a config entry."""
    coordinator = StarlinkCoordinator(hass, entry)

    # async_config_entry_first_refresh() runs the coordinator's _async_setup()
    # (session priming + hardware discovery) once and then performs the first
    # poll. Calling _async_setup() here as well would prime the session and
    # rediscover the hardware a second time on every start.
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry, e.g. for a reload after a cookie change."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # pop() with a default: unloading must not raise when the entry was
        # never stored (the first refresh failed) or is already gone.
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the stored Starlink session material when the entry is removed.

    The cookie in the config entry is a credential for the Starlink account and
    must not outlive the integration, so every credential file is deleted here.
    The hardware-discovery metrics are deliberately kept: a later re-install
    finds the same dish and router again and the entities therefore continue
    instead of being created as new ones.
    """
    removed = await hass.async_add_executor_job(storage.purge_session_data, hass)
    if removed:
        _LOGGER.info(
            "Deleted %d stored credential file(s) after the entry was removed",
            len(removed),
        )
    else:
        _LOGGER.debug("No stored session material to delete for the removed entry")

    # The "session expired" repair belongs to an entry that no longer exists.
    ir.async_delete_issue(hass, DOMAIN, ISSUE_SESSION_EXPIRED)
