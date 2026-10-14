"""Set up the Starlink Remote integration and clean up after it.

The integration can be added more than once, so every account-scoped thing it
owns is keyed on the config entry: the stored cookie, the discovery history,
the entity unique ids, the device identifiers, the repair issue and the
notification. That way several entries - several Starlink accounts, or the same
account added twice - poll side by side without sharing one piece of state.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from . import notify, storage
from .config_flow import entry_title
from .const import CONF_COOKIE, DEFAULT_TITLE, DOMAIN
from .coordinator import StarlinkCoordinator
from .session import account_number_from_cookie

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.BUTTON,
]

#: Config entry version written by this integration (see async_migrate_entry).
ENTRY_VERSION = 3


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an old config entry.

    Version 2 added the account number as the unique id of the entry. Version 3
    made everything account-scoped start with the config entry id, so a second
    entry (a second account, or the same account added again) no longer
    overwrites the first entry's cookie and no longer has its entities refused
    as duplicates of the first entry's.
    """
    if entry.version > ENTRY_VERSION:
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

    if entry.version == 2:
        await _async_migrate_storage(hass, entry)
        await _async_migrate_registry_identity(hass, entry)
        _adopt_account_title(hass, entry)
        hass.config_entries.async_update_entry(entry, version=ENTRY_VERSION)

    _LOGGER.debug(
        "Migrated Starlink Remote entry %s to version %s", entry.entry_id, entry.version
    )
    return True


async def _async_migrate_storage(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Move the files of the single-entry layout into this entry's directory."""
    account_number = account_number_from_cookie(entry.data.get(CONF_COOKIE, ""))
    sole_entry = len(hass.config_entries.async_entries(DOMAIN)) == 1
    moved = await hass.async_add_executor_job(
        storage.migrate_legacy_files, hass, entry.entry_id, account_number, sole_entry
    )
    if moved:
        _LOGGER.info(
            "Adopted %d stored session file(s) into the directory of %s",
            len(moved),
            entry.title,
        )


def _adopt_account_title(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Give a pre-multi-account entry the title that names its account.

    Entries created before version 3 all carry the plain default title, which
    makes several accounts indistinguishable in the entry list, in the repair
    issue and in the session-expired notification. Only an untouched default
    title is replaced: a title the user chose is left alone.
    """
    if entry.title != DEFAULT_TITLE:
        return
    account_number = account_number_from_cookie(entry.data.get(CONF_COOKIE, ""))
    if not account_number:
        return
    hass.config_entries.async_update_entry(
        entry, title=entry_title(hass, account_number)
    )


async def _async_migrate_registry_identity(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Prefix this entry's entities and devices with its config entry id.

    Before version 3 the entity unique ids and device identifiers were only the
    hardware (target) id, so two entries describing the same hardware collided:
    Home Assistant refused the second entry's entities as duplicates of the
    first entry's devices. Re-stamping the existing rows keeps the entities,
    their entity ids, their names and their recorded history in place, instead
    of letting them be recreated as new ones.
    """
    prefix = f"{entry.entry_id}_"

    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        legacy_targets = {
            identifier[1]
            for identifier in device.identifiers
            if identifier[0] == DOMAIN and not identifier[1].startswith(prefix)
        }
        if not legacy_targets:
            continue
        identifiers = {
            identifier
            for identifier in device.identifiers
            if not (identifier[0] == DOMAIN and identifier[1] in legacy_targets)
        }
        identifiers.update((DOMAIN, f"{prefix}{target}") for target in legacy_targets)
        try:
            device_registry.async_update_device(device.id, new_identifiers=identifiers)
        except (TypeError, ValueError) as err:
            # A core without the new_identifiers keyword leaves the device row
            # alone; the device is then registered under the scoped identifier
            # on the next poll, with the entities following it.
            _LOGGER.warning("Could not re-scope device %s: %s", device.id, err)

    entity_registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if entity.unique_id.startswith(prefix):
            continue
        try:
            entity_registry.async_update_entity(
                entity.entity_id, new_unique_id=f"{prefix}{entity.unique_id}"
            )
        except ValueError as err:
            _LOGGER.warning(
                "Could not re-scope entity %s: %s", entity.entity_id, err
            )

    _LOGGER.debug("Scoped the registry rows of %s to its entry id", entry.title)


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
    """Delete the stored session material of *this* entry.

    The cookie in the config entry is a credential for the Starlink account and
    must not outlive the integration, so the credential file of this entry is
    deleted here. The hardware-discovery metrics are deliberately kept: a later
    re-install finds the same dish and router again and the entities therefore
    continue instead of being created as new ones. Only this entry's directory
    is touched - removing one account leaves the other accounts signed in.
    """
    removed = await hass.async_add_executor_job(
        storage.purge_session_data, hass, entry.entry_id
    )
    if removed:
        _LOGGER.info(
            "Deleted %d stored credential file(s) after the entry was removed",
            len(removed),
        )
    else:
        _LOGGER.debug("No stored session material to delete for the removed entry")

    # Only the alerts of the removed entry: the repair issue and the
    # notification of another account must survive this removal.
    await notify.async_remove_entry_alerts(hass, entry.entry_id)
