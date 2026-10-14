"""Sensor platform for Starlink Remote.

Every sensor is described once in ``SENSOR_DESCRIPTIONS``. A description is
bound either to a device (``dev_types``) or to the account as a whole
(``"global"``); ``async_setup_entry`` turns the descriptions into entities for
each device the coordinator has discovered.

Entity names come from ``translation_key`` (see ``strings.json`` under
``entity.sensor``), so the names stay localisable while the entity ids keep the
``<device>_<name>`` shape Home Assistant derives from them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DATA_DEVICES, DATA_USAGE, DATA_WIFI_CLIENTS, DOMAIN
from .entity_base import StarlinkEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class StarlinkSensorEntityDescription(SensorEntityDescription):
    """A Starlink sensor plus how to read its value out of the poll payload."""

    #: Reads the value out of a device payload (or the whole coordinator data
    #: for global descriptions).
    value_fn: Callable[[dict[str, Any]], StateType] = lambda x: None
    #: Extra attributes for the entity, read from the same payload.
    attr_fn: Callable[[dict[str, Any]], dict[str, Any]] = lambda x: {}
    #: Device types the sensor is created for, or ("global",) for account-wide
    #: sensors which are created once per config entry.
    dev_types: tuple[str, ...] = ()



def _uptime_seconds(device: dict[str, Any]) -> float | None:
    """Return the uptime exactly as the API reports it.

    The value stays in the API's own unit (seconds) so the recorder keeps one
    continuous series; the sensor suggests hours for the display.
    """
    value = (device.get("status", {}).get("device_state", {}) or {}).get("uptime_s")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _uptime_hours(device: dict[str, Any]) -> float | None:
    """Return the uptime in hours, the unit this entity is declared in."""
    seconds = _uptime_seconds(device)
    return round(seconds / 3600, 2) if seconds is not None else None


def _uptime_attributes(device: dict[str, Any]) -> dict[str, Any]:
    """Return the uptime in seconds, the raw API value."""
    seconds = (device.get("status", {}).get("device_state", {}) or {}).get("uptime_s")
    return {"uptime_seconds": seconds}


def _wifi_client_count(device: dict[str, Any]) -> StateType:
    """Return the number of clients on a router.

    Two shapes can answer this: a client *list* (a firmware that reports one
    over gRPC, the richer payload) and the account telemetry *counts*. Both
    answer the same question, so whichever arrived is used.
    """
    clients = device.get(DATA_WIFI_CLIENTS)
    if isinstance(clients, list):
        return len(clients)
    if isinstance(clients, dict):
        return clients.get("count")
    return None


def _wifi_client_attributes(device: dict[str, Any]) -> dict[str, Any]:
    """Return the per-band detail that sits next to the client count."""
    clients = device.get(DATA_WIFI_CLIENTS)
    attributes: dict[str, Any] = {}
    if isinstance(clients, list):
        attributes["client_list"] = [
            f"{c.get('name') or c.get('given_name') or c.get('mac_address')} "
            f"({c.get('ip_address')})"
            for c in clients
        ]
    elif isinstance(clients, dict):
        attributes["clients_2ghz"] = clients.get("count_2ghz")
        attributes["clients_5ghz"] = clients.get("count_5ghz")
        attributes["clients_ethernet"] = clients.get("count_ethernet")
        attributes["wan_rx_bytes"] = clients.get("wan_rx_bytes")
        attributes["wan_tx_bytes"] = clients.get("wan_tx_bytes")
        attributes["wifi_bypassed"] = clients.get("bypassed")
        attributes["software_version"] = clients.get("software_version")
    attributes["ping_history"] = device.get("history", {}).get("ping_latency_ms", [])[-10:]
    return attributes

SENSOR_DESCRIPTIONS: tuple[StarlinkSensorEntityDescription, ...] = (
    # Account-wide.
    StarlinkSensorEntityDescription(
        key="data_usage_total",
        translation_key="data_usage_total",
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.get(DATA_USAGE, {}).get("total_gb"),
        attr_fn=lambda d: {
            "billing_cycle_start": d.get(DATA_USAGE, {}).get("cycle_start"),
            "billing_cycle_end": d.get(DATA_USAGE, {}).get("cycle_end"),
            "plan_bucket": d.get(DATA_USAGE, {}).get("bucket"),
            "usage_limit_gb": d.get(DATA_USAGE, {}).get("limit_gb"),
            "daily_usage_gb": d.get(DATA_USAGE, {}).get("daily_gb"),
        },
        dev_types=("global",),
    ),
    StarlinkSensorEntityDescription(
        key="state",
        translation_key="state",
        value_fn=lambda d: d.get("status", {}).get("state"),
        dev_types=("dish", "router"),
    ),
    StarlinkSensorEntityDescription(
        key="uptime",
        translation_key="uptime",
        # Deliberately no SensorDeviceClass.DURATION: Home Assistant converts a
        # duration into the unit system's unit, which is seconds in metric, so
        # the reading would show seconds whatever unit were declared. A plain
        # hour unit shows the reading in the unit the dish is read in.
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_uptime_hours,
        attr_fn=_uptime_attributes,
        dev_types=("dish", "router"),
    ),
    # Dish only.
    StarlinkSensorEntityDescription(
        key="downlink_throughput",
        translation_key="downlink_throughput",
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: round(
            float(d.get("status", {}).get("downlink_throughput_bps", 0)) / 1e6, 2
        ),
        dev_types=("dish",),
    ),
    StarlinkSensorEntityDescription(
        key="uplink_throughput",
        translation_key="uplink_throughput",
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: round(
            float(d.get("status", {}).get("uplink_throughput_bps", 0)) / 1e6, 2
        ),
        dev_types=("dish",),
    ),
    StarlinkSensorEntityDescription(
        key="ping_latency",
        translation_key="ping_latency",
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("status", {}).get("pop_ping_latency_ms"),
        dev_types=("dish",),
    ),
    StarlinkSensorEntityDescription(
        key="obstruction_fraction",
        translation_key="obstruction_fraction",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (
            round(
                float(
                    d.get("status", {})
                    .get("obstruction_stats", {})
                    .get("fraction_obstructed", 0)
                )
                * 100.0,
                2,
            )
            if d.get("status", {}).get("obstruction_stats")
            else None
        ),
        dev_types=("dish",),
    ),
    StarlinkSensorEntityDescription(
        key="boresight_azimuth",
        translation_key="boresight_azimuth",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("status", {}).get("boresight_azimuth_deg"),
        dev_types=("dish",),
    ),
    StarlinkSensorEntityDescription(
        key="tilt_angle",
        translation_key="tilt_angle",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("status", {})
        .get("alignment_stats", {})
        .get("tilt_angle_deg"),
        dev_types=("dish",),
    ),
    # Dish event log.
    StarlinkSensorEntityDescription(
        key="bootcount",
        translation_key="bootcount",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("status", {}).get("device_info", {}).get("bootcount"),
        dev_types=("dish",),
    ),
    StarlinkSensorEntityDescription(
        key="searching_events",
        translation_key="searching_events",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: len(
            [
                o
                for o in d.get("history", {}).get("outages", [])
                if o.get("cause") == "SEARCHING"
            ]
        ),
        attr_fn=lambda d: {
            "outages": [
                o
                for o in d.get("history", {}).get("outages", [])
                if o.get("cause") == "SEARCHING"
            ]
        },
        dev_types=("dish",),
    ),
    StarlinkSensorEntityDescription(
        key="total_outages",
        translation_key="total_outages",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: len(d.get("history", {}).get("outages", [])),
        attr_fn=lambda d: {"outages": d.get("history", {}).get("outages", [])},
        dev_types=("dish",),
    ),
    # Router only.
    StarlinkSensorEntityDescription(
        key="wifi_clients",
        translation_key="wifi_clients",
        icon="mdi:wifi",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_wifi_client_count,
        attr_fn=_wifi_client_attributes,
        dev_types=("router",),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: Any, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the sensors for every device the coordinator discovered."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    devices: dict[str, dict[str, Any]] = coordinator.data.get(DATA_DEVICES, {})

    entities: list[StarlinkDeviceSensor] = []

    # Account-wide sensors need one host device to hang off. A dish is preferred
    # (it is the device the account figure belongs to); otherwise the router.
    host_id = next(
        (tid for tid, dev in devices.items() if dev.get("type") == "dish"),
        next(iter(devices), None),
    )
    if host_id is not None:
        for desc in SENSOR_DESCRIPTIONS:
            if "global" in desc.dev_types:
                entities.append(StarlinkDeviceSensor(coordinator, desc, host_id))

    for target_id, dev_data in devices.items():
        dev_type = dev_data.get("type")
        for desc in SENSOR_DESCRIPTIONS:
            if dev_type in desc.dev_types:
                entities.append(StarlinkDeviceSensor(coordinator, desc, target_id))

    async_add_entities(entities)


class StarlinkDeviceSensor(StarlinkEntity, SensorEntity):
    """A single sensor reading of one Starlink device."""

    entity_description: StarlinkSensorEntityDescription

    @property
    def native_value(self) -> StateType:
        """Return the value, preferring the account-wide payload for globals."""
        if "global" in self.entity_description.dev_types:
            value = self.entity_description.value_fn(self.coordinator.data)
            if value is not None:
                return value

        dev_data = self.coordinator.data.get(DATA_DEVICES, {}).get(self.target_id, {})
        return self.entity_description.value_fn(dev_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the description's extra attributes for this device."""
        try:
            if "global" in self.entity_description.dev_types:
                # Account-wide descriptions read the whole payload, exactly as
                # native_value does for them.
                return self.entity_description.attr_fn(self.coordinator.data)
            dev_data = self.coordinator.data.get(DATA_DEVICES, {}).get(
                self.target_id, {}
            )
            return self.entity_description.attr_fn(dev_data)
        except Exception:  # pylint: disable=broad-except
            return {}
