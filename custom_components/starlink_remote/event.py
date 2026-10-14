"""Event platform for Starlink Remote.

The API is polled, and what it hands back are counters, codes and samples -
not events. The events a user cares about (the dish rebooted, it lost its sky,
an obstruction outage started, an alert came up, the router gave up on a
software update, a Wi-Fi client left) are therefore the differences *between
two polls*, detected here and published as Home Assistant event entities so
they reach the logbook and automations.

Nothing in here touches the local network: the same account polling as the rest
of the integration feeds these entities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_DEVICES, DOMAIN
from .entity_base import StarlinkEntity

#: Every event type this platform can report. Home Assistant wants the full set
#: up front, so each cause the API is known to use has a type of its own and
#: anything unrecognised falls back to ``outage``.
EVENT_TYPES = (
    "rebooted",
    "state_changed",
    "searching",
    "obstructed",
    "outage",
    "alert",
    "update_state_changed",
    "clients_changed",
)


def detect_events(
    previous: dict[str, Any], current: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return the events that happened between two polls of one device.

    Pure: both arguments are per-device payloads as the coordinator publishes
    them. An empty ``previous`` yields nothing - the first poll is only a
    baseline, the world existing is not an event.
    """
    if not previous:
        return []

    events: list[dict[str, Any]] = []
    prev_status = previous.get("status") or {}
    cur_status = current.get("status") or {}

    # A reboot. The dish counts its boots in device_info; the router exposes no
    # such counter, so a drop in uptime is the equivalent signal there.
    prev_boot = (prev_status.get("device_info") or {}).get("bootcount")
    cur_boot = (cur_status.get("device_info") or {}).get("bootcount")
    prev_uptime, cur_uptime = _uptime(prev_status), _uptime(cur_status)
    if (
        prev_boot is not None and cur_boot is not None and cur_boot > prev_boot
    ) or (
        prev_uptime is not None
        and cur_uptime is not None
        and cur_uptime < prev_uptime
    ):
        events.append(
            {
                "event_type": "rebooted",
                "attributes": {"bootcount": cur_boot, "uptime_s": cur_uptime},
            }
        )

    # The state the app would show: CONNECTED, or the disablement code.
    if prev_status.get("state") != cur_status.get("state") and cur_status.get("state"):
        events.append(
            {
                "event_type": "state_changed",
                "attributes": {
                    "from": prev_status.get("state"),
                    "to": cur_status.get("state"),
                },
            }
        )

    # Outages the dish logged since the last poll, keyed by cause and start so
    # the same outage is reported once.
    seen = _outage_keys(previous)
    for outage in (current.get("history") or {}).get("outages") or []:
        if not isinstance(outage, dict) or _outage_key(outage) in seen:
            continue
        cause = str(outage.get("cause") or "").lower()
        events.append(
            {
                "event_type": cause if cause in ("searching", "obstructed") else "outage",
                "attributes": {
                    "cause": outage.get("cause"),
                    "duration_s": outage.get("duration_s") or outage.get("duration"),
                    "started": outage.get("start") or outage.get("started"),
                },
            }
        )

    # Alerts: the dish reports a map of flags, the router's arrive as the
    # account telemetry's ActiveAlerts list.
    for name in _alert_names(cur_status.get("alerts")) - _alert_names(
        prev_status.get("alerts")
    ):
        events.append(
            {"event_type": "alert", "attributes": {"alert": name, "source": "dish"}}
        )
    for name in _alert_names(current.get("alerts")) - _alert_names(previous.get("alerts")):
        events.append(
            {"event_type": "alert", "attributes": {"alert": name, "source": "router"}}
        )

    # Software update progress (the router reports its failures here).
    prev_update, cur_update = _update_state(prev_status), _update_state(cur_status)
    if prev_update != cur_update and (prev_update or cur_update):
        events.append(
            {
                "event_type": "update_state_changed",
                "attributes": {"from": prev_update, "to": cur_update},
            }
        )

    # Wi-Fi clients coming and going. Only the count is published by the API, so
    # the event identifies the delta and not the client.
    prev_clients, cur_clients = _client_count(previous), _client_count(current)
    if prev_clients is not None and cur_clients is not None and prev_clients != cur_clients:
        events.append(
            {
                "event_type": "clients_changed",
                "attributes": {"from": prev_clients, "to": cur_clients},
            }
        )

    return events


def _uptime(status: dict[str, Any]) -> float | None:
    """Return a status payload's uptime in seconds."""
    value = (status.get("device_state") or {}).get("uptime_s")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _outage_key(outage: dict[str, Any]) -> str:
    """Return a stable key for one outage entry."""
    start = outage.get("start") or outage.get("started") or ""
    return f"{start}|{outage.get('cause')}"


def _outage_keys(device: dict[str, Any]) -> set[str]:
    """Return the outage keys already present in a payload."""
    return {
        _outage_key(outage)
        for outage in (device.get("history") or {}).get("outages") or []
        if isinstance(outage, dict)
    }


def _alert_names(alerts: Any) -> set[str]:
    """Flatten whichever shape the API used for alerts into plain names."""
    if isinstance(alerts, dict):
        return {str(name) for name, active in alerts.items() if active}
    if isinstance(alerts, (list, tuple)):
        names: set[str] = set()
        for item in alerts:
            if isinstance(item, str):
                names.add(item)
            elif isinstance(item, dict):
                named = item.get("name") or item.get("alert") or item.get("id")
                names.add(str(named) if named else str(sorted(item)))
        return names
    return set()


def _update_state(status: dict[str, Any]) -> str | None:
    """Return the software update state of a device, router or dish spelling."""
    stats = status.get("software_update_stats") or {}
    value = stats.get("state") or stats.get("software_update_state")
    return str(value) if value else None


def _client_count(device: dict[str, Any]) -> int | None:
    """Return the client count published for a router, list or counts shape."""
    clients = device.get("wifi_clients")
    if isinstance(clients, list):
        return len(clients)
    if isinstance(clients, dict):
        return clients.get("count")
    return None


@dataclass(frozen=True, kw_only=True)
class StarlinkEventEntityDescription(EventEntityDescription):
    """Description of a Starlink event entity."""

    dev_types: tuple[str, ...] = ()


EVENT_DESCRIPTIONS = (
    StarlinkEventEntityDescription(
        key="events",
        translation_key="events",
        icon="mdi:timeline-clock-outline",
        event_types=EVENT_TYPES,
        dev_types=("dish", "router"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: Any, async_add_entities: AddEntitiesCallback
) -> None:
    """Create one event entity per device the coordinator discovered."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    devices: dict[str, dict[str, Any]] = coordinator.data.get(DATA_DEVICES, {})

    entities: list[StarlinkEventEntity] = []
    for target_id, dev_data in devices.items():
        for desc in EVENT_DESCRIPTIONS:
            if dev_data.get("type") in desc.dev_types:
                entities.append(StarlinkEventEntity(coordinator, desc, target_id))

    async_add_entities(entities)


class StarlinkEventEntity(StarlinkEntity, EventEntity):
    """The last event observed on one Starlink device.

    Each coordinator update is compared with the previous payload, and every
    difference becomes an event. The first poll after a start only records the
    baseline.
    """

    entity_description: StarlinkEventEntityDescription

    def __init__(self, coordinator: Any, description: Any, target_id: str) -> None:
        """Initialize the entity with an empty baseline."""
        super().__init__(coordinator, description, target_id)
        self._previous: dict[str, Any] = {}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Publish the differences between this poll and the last one."""
        current = (
            self.coordinator.data.get(DATA_DEVICES, {}).get(self.target_id, {})
        )
        previous, self._previous = self._previous, current
        for event in detect_events(previous, current):
            self._trigger_event(event["event_type"], event["attributes"])
        super()._handle_coordinator_update()
