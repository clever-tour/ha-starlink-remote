"""Diagnostics support for Starlink Remote.

Settings > Devices & Services > Starlink Remote > Download diagnostics produces
this file. It contains what is needed to debug a report - coordinator state,
device keys, session health - and deliberately contains no credential: the
cookie is redacted even though the file is only handed to the user who asked
for it, because diagnostics get pasted into public issues.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_COOKIE, DATA_DEVICES, DATA_USAGE, DOMAIN

#: Values that are personal data rather than debugging context.
TO_REDACT = {CONF_COOKIE, "title", "id", "discovered_ids"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    devices: dict[str, Any] = (
        _summarize_devices(coordinator) if coordinator is not None else {}
    )

    # The entry title carries the last 8 characters of the account number
    # (see config_flow.entry_title), and diagnostics are routinely pasted into
    # public issues - so the title and every hardware id are redacted too.
    return async_redact_data(
        {
        "entry": {
            "title": entry.title,
            "state": str(entry.state),
            "data_keys": sorted(entry.data),
            "cookie": _redact(entry.data.get(CONF_COOKIE)),
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": getattr(coordinator, "last_update_success", None),
            "update_interval": str(getattr(coordinator, "update_interval", None)),
            "discovered_ids": sorted(getattr(coordinator, "discovered_ids", [])),
            "auth_failure_active": getattr(coordinator, "_auth_failure_start", None)
            is not None,
            "service_lines_available": getattr(coordinator, "_service_lines", None)
            is not None,
        },
        "data_usage": _usage_digest(coordinator),
        "devices": devices,
        },
        TO_REDACT,
    )


def _usage_digest(coordinator: Any) -> dict[str, Any]:
    """Describe the resolved account data usage: the figures, not the payload."""
    if coordinator is None:
        return {}
    usage = (getattr(coordinator, "data", None) or {}).get(DATA_USAGE) or {}
    return {
        "total_gb": usage.get("total_gb"),
        "source": usage.get("source"),
        "billing_cycle_start": usage.get("cycle_start"),
        "billing_cycle_end": usage.get("cycle_end"),
        "usage_limit_gb": usage.get("limit_gb"),
        "plan_bucket": usage.get("bucket"),
        "days_reported": len(usage.get("daily_gb") or []),
    }


def _summarize_devices(coordinator: Any) -> dict[str, Any]:
    """Describe the polled devices without dumping every telemetry value."""
    summary: dict[str, Any] = {}
    # Device keys are hardware ids; number them instead of publishing them.
    for index, (_target_id, device) in enumerate(
        coordinator.data.get(DATA_DEVICES, {}).items(), start=1
    ):
        status = device.get("status", {})
        summary[f"device_{index}"] = {
            "type": device.get("type"),
            "status_keys": sorted(status),
            "history_keys": sorted(device.get("history", {})),
            "device_info": status.get("device_info", {}),
        }
    return summary


def _redact(value: Any) -> str | None:
    """Describe a stored credential without revealing it."""
    if not value:
        return None
    return f"<redacted {len(str(value))} characters>"
