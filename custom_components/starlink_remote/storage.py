"""On-disk session state for the Starlink Remote integration.

Everything the integration keeps between restarts lives below one directory,
``<config>/.storage/<STORAGE_DIR>``, and falls into exactly two categories:

* **Session material** - the starlink.com browser cookie harvested by the
  config flow (``cookie.txt``). This is a credential: it is written with
  owner-only permissions and deleted the moment the config entry is removed
  (see :func:`purge_session_data`).
* **Historic metrics** - the hardware ids discovered on the account
  (``history_persistence.json``). It is not a credential, and it deliberately
  survives the removal of the entry: a later re-install rediscovers the same
  dish/router, so the entities keep their identity and their recorded history
  instead of being recreated from scratch.

Both live in a **per config entry directory** (``<STORAGE_DIR>/<entry_id>``),
so several entries - several Starlink accounts, or the same account added
twice - keep their own cookie and their own discovery history instead of
overwriting each other's. Entries created before that layout (version 2) are
moved into their directory by :func:`migrate_legacy_files`.

Every other module talks to the files through this module, so the file names,
the permission bits, the layout and the purge policy are defined in one place.
"""
from __future__ import annotations

import json
import logging
import os

from homeassistant.core import HomeAssistant

from .const import CONF_COOKIE_FILE, STORAGE_DIR
from .session import account_number_from_cookie

_LOGGER = logging.getLogger(__name__)

#: Discovered hardware ids, kept across a removal of the config entry.
HISTORY_FILE = "history_persistence.json"

#: Files that hold a starlink.com credential and must never be kept around
#: after the entry that owns the session is gone.
SESSION_FILES = (CONF_COOKIE_FILE,)

#: Never deleted by :func:`purge_session_data`.
_KEEP_ON_PURGE = frozenset({HISTORY_FILE})

#: The cookie is a credential; nobody else on the box has a reason to read it.
_COOKIE_MODE = 0o600


def storage_dir(hass: HomeAssistant) -> str:
    """Return the directory holding all persisted integration state."""
    return hass.config.path(".storage", STORAGE_DIR)


def entry_dir(hass: HomeAssistant, entry_id: str) -> str:
    """Return the directory that holds the state of one config entry."""
    return os.path.join(storage_dir(hass), entry_id)


def cookie_path(hass: HomeAssistant, entry_id: str) -> str:
    """Return the path of the persisted starlink.com session cookie."""
    return os.path.join(entry_dir(hass, entry_id), CONF_COOKIE_FILE)


def history_path(hass: HomeAssistant, entry_id: str) -> str:
    """Return the path of the persisted hardware-discovery metrics."""
    return os.path.join(entry_dir(hass, entry_id), HISTORY_FILE)


def save_cookie(hass: HomeAssistant, entry_id: str, cookie: str) -> None:
    """Persist the session cookie, readable by the owner only (SyncWorker).

    An empty cookie removes the file: writing a zero-length credential would
    only leave a file that pretends a session exists.
    """
    path = cookie_path(hass, entry_id)
    if not cookie:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as err:
            _LOGGER.error("Failed to remove the session cookie file: %s", err)
        return

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # os.open() applies the mode on creation, chmod() fixes up a file that
        # already exists from an older version of the integration.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _COOKIE_MODE)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(cookie)
        os.chmod(path, _COOKIE_MODE)
    except OSError as err:
        _LOGGER.error("Failed to store the session cookie: %s", err)
    else:
        _LOGGER.debug("Session cookie stored in %s", path)


def load_cookie(hass: HomeAssistant, entry_id: str) -> str:
    """Return the persisted session cookie, or an empty string when absent."""
    try:
        with open(cookie_path(hass, entry_id), encoding="utf-8") as handle:
            return handle.read().strip()
    except FileNotFoundError:
        return ""
    except OSError as err:
        _LOGGER.error("Failed to read the persisted session cookie: %s", err)
        return ""


def load_discovered_ids(hass: HomeAssistant, entry_id: str) -> set[str]:
    """Return the hardware ids discovered on previous runs (empty when none)."""
    try:
        with open(history_path(hass, entry_id), encoding="utf-8") as handle:
            history = json_load(handle.read())
    except FileNotFoundError:
        return set()
    except OSError as err:
        _LOGGER.error("Failed to read the hardware history: %s", err)
        return set()

    discovered = history.get("discovered_ids", [])
    if not isinstance(discovered, list):
        _LOGGER.warning("Hardware history is malformed, ignoring it")
        return set()
    return {str(target_id) for target_id in discovered}


def save_discovered_ids(hass: HomeAssistant, entry_id: str, ids: set[str]) -> None:
    """Persist the discovered hardware ids (SyncWorker)."""
    path = history_path(hass, entry_id)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json_dump({"discovered_ids": sorted(ids)}))
    except OSError as err:
        _LOGGER.error("Failed to store the hardware history: %s", err)


def purge_session_data(hass: HomeAssistant, entry_id: str) -> list[str]:
    """Delete the stored credential of one entry, keeping its metrics.

    Called when the config entry is removed: the user asked for the
    starlink.com key material to disappear with the integration, while the
    non-sensitive discovery history stays behind. Only the directory of
    ``entry_id`` is touched, so removing one account cannot log out another.
    Returns the paths removed.
    """
    directory = entry_dir(hass, entry_id)
    try:
        names = os.listdir(directory)
    except FileNotFoundError:
        return []
    except OSError as err:
        _LOGGER.error("Failed to inspect %s: %s", directory, err)
        return []

    removed: list[str] = []
    for name in names:
        path = os.path.join(directory, name)
        if name in _KEEP_ON_PURGE:
            continue
        if not os.path.isfile(path):
            # Only files are ever written here; leave anything unexpected alone.
            _LOGGER.debug("Skipping non-file %s while purging session data", path)
            continue
        try:
            os.remove(path)
            removed.append(path)
        except OSError as err:
            _LOGGER.error("Failed to remove %s: %s", path, err)

    # Tidy the directory away as well, but only when it ended up empty: with
    # the metrics file still inside os.rmdir() fails and the file stays put.
    try:
        os.rmdir(directory)
    except OSError:
        pass

    return removed


def migrate_legacy_files(
    hass: HomeAssistant, entry_id: str, account: str | None, sole_entry: bool
) -> list[str]:
    """Move pre-version-3 flat storage into the entry's own directory.

    Version 2 kept exactly one cookie and one history file for every entry,
    directly below ``<STORAGE_DIR>``. The files therefore cannot simply be
    handed to the first entry that migrates: with two accounts the cookie in
    the flat layout belongs to the account it names. It is matched through the
    account number in the cookie; when the cookie carries none, it is only
    claimed by an entry that is the sole entry for the domain. A history file
    is only moved together with a claimed cookie, so no account inherits the
    hardware ids of another. Returns the paths moved.
    """
    legacy = storage_dir(hass)
    cookie_src = os.path.join(legacy, CONF_COOKIE_FILE)
    history_src = os.path.join(legacy, HISTORY_FILE)
    cookie_dst = cookie_path(hass, entry_id)
    history_dst = history_path(hass, entry_id)

    if not os.path.isfile(cookie_src) and not os.path.isfile(history_src):
        return []

    raw = ""
    if os.path.isfile(cookie_src):
        try:
            with open(cookie_src, encoding="utf-8") as handle:
                raw = handle.read().strip()
        except OSError as err:
            _LOGGER.error("Failed to read the legacy cookie file: %s", err)
            return []

    if raw:
        legacy_account = account_number_from_cookie(raw)
        if legacy_account and account and legacy_account != account:
            _LOGGER.debug(
                "Legacy cookie belongs to another account, leaving it for its "
                "own entry to migrate"
            )
            return []
        if legacy_account is None and not sole_entry:
            _LOGGER.warning(
                "The legacy cookie file names no account and several Starlink "
                "Remote entries exist; keeping it out of the way instead of "
                "guessing which entry owns it"
            )
            return []

    moved: list[str] = []
    for source, destination in (
        (cookie_src, cookie_dst),
        (history_src, history_dst),
    ):
        if not os.path.isfile(source) or os.path.exists(destination):
            continue
        try:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            os.replace(source, destination)
        except OSError as err:
            _LOGGER.error("Failed to move %s into %s: %s", source, destination, err)
            continue
        moved.append(destination)

    if moved:
        _LOGGER.info(
            "Moved %d stored file(s) of the single-entry layout into the "
            "directory of entry %s",
            len(moved),
            entry_id,
        )
    # Tidy the flat directory away when nothing is left in it.
    try:
        os.rmdir(legacy)
    except OSError:
        pass
    return moved


def json_dump(payload: dict[str, object]) -> str:
    """Serialise the metrics file with stable, diff-friendly formatting."""
    return json.dumps(payload, indent=2)


def json_load(raw: str) -> dict[str, object]:
    """Parse the metrics file, returning an empty mapping when it is broken."""
    try:
        parsed = json.loads(raw)
    except ValueError:
        _LOGGER.warning("Hardware history is not valid JSON, starting empty")
        return {}
    return parsed if isinstance(parsed, dict) else {}
