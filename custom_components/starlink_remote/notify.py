"""User-facing alerts for a Starlink session the account API no longer accepts.

Two channels are raised together and both are keyed on the config entry, so
every configuration entry - every Starlink account - owns its own pair of
alerts and a healthy account leaves nothing behind:

* a **fixable Repairs issue** - the durable channel. It is listed under
  Settings > System > Repairs with the cookie dialog behind its Fix button, and
  Home Assistant keeps it until the session works again.
* a **persistent notification** - the immediate channel. It is shown in the
  notification panel, carries links straight into Home Assistant, disappears
  on its own as soon as a session is accepted again, and the user can dismiss
  it at any time.

Raising and clearing go through this module so both channels always appear and
disappear together, and so the texts live in one place.
"""
from __future__ import annotations

import logging

from homeassistant.components import persistent_notification as pn
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, ISSUE_SESSION_EXPIRED

_LOGGER = logging.getLogger(__name__)

#: UI targets the notification links to: the repair panel that holds the fix
#: flow, and the integration page that holds the same dialog behind the gear.
REPAIRS_URL = "/config/repairs"
INTEGRATION_URL = f"/config/integrations/integration/{DOMAIN}"


def issue_id(entry_id: str) -> str:
    """Return the repair issue id that belongs to ``entry_id``."""
    return f"{ISSUE_SESSION_EXPIRED}_{entry_id}"


def notification_id(entry_id: str) -> str:
    """Return the persistent notification id that belongs to ``entry_id``."""
    return f"{DOMAIN}_{ISSUE_SESSION_EXPIRED}_{entry_id}"


def _message(entry: ConfigEntry, detail: str) -> str:
    """Render the notification body for ``entry``.

    Kept as markdown: the notification panel renders links, so the two paths to
    the fix are one click away.
    """
    suffix = f" {detail}" if detail else ""
    return (
        f"Home Assistant can no longer poll the Starlink account "
        f"**{entry.title}**: the stored starlink.com cookie is not accepted "
        f"anymore.{suffix}\n\n"
        f"[Renew the cookie]({REPAIRS_URL}) · "
        f"[Open the integration]({INTEGRATION_URL})\n\n"
        f"Sign in at starlink.com, copy the `cookie` request header from your "
        f"browser and paste it into the dialog. The last known values stay "
        f"visible until then, and this notice clears itself once a session is "
        f"accepted again - or dismiss it here if you prefer."
    )


async def async_raise_session_alerts(
    hass: HomeAssistant, entry: ConfigEntry, detail: str = ""
) -> None:
    """Raise the repair issue and the notification for ``entry`` (event loop)."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id(entry.entry_id),
        is_fixable=True,
        is_persistent=True,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_SESSION_EXPIRED,
        translation_placeholders={"account": entry.title},
        data={"entry_id": entry.entry_id},
    )
    pn.async_create(
        hass,
        _message(entry, detail),
        title=f"Starlink session expired ({entry.title})",
        notification_id=notification_id(entry.entry_id),
    )
    _LOGGER.debug("Raised the session-expired alerts for %s", entry.title)


async def async_clear_session_alerts(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Drop both alerts of ``entry`` (event loop)."""
    ir.async_delete_issue(hass, DOMAIN, issue_id(entry.entry_id))
    pn.async_dismiss(hass, notification_id(entry.entry_id))


async def async_remove_entry_alerts(hass: HomeAssistant, entry_id: str) -> None:
    """Drop both alerts of an entry that is being removed (event loop)."""
    ir.async_delete_issue(hass, DOMAIN, issue_id(entry_id))
    pn.async_dismiss(hass, notification_id(entry_id))
