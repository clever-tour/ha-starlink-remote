from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Callable
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import UnitOfDataRate, UnitOfTime, UnitOfInformation, PERCENTAGE, DEGREE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from .const import DATA_DISH_STATUS, DATA_DISH_HISTORY, DATA_WIFI_CLIENTS, DATA_USAGE, DOMAIN
from .entity_base import StarlinkEntity

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class StarlinkSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], StateType] = lambda x: None
    attr_fn: Callable[[dict[str, Any]], dict[str, Any]] = lambda x: {}

SENSORS = (
    StarlinkSensorEntityDescription(key='state', name='State', value_fn=lambda d: d.get(DATA_DISH_STATUS, {}).get('state')),
    StarlinkSensorEntityDescription(
        key='downlink_throughput', 
        name='Downlink Throughput', 
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND, 
        device_class=SensorDeviceClass.DATA_RATE, 
        state_class=SensorStateClass.MEASUREMENT, 
        value_fn=lambda d: round(float(d.get(DATA_DISH_STATUS, {}).get('downlink_throughput_bps', 0)) / 1000000.0, 2)
    ),
    StarlinkSensorEntityDescription(
        key='uplink_throughput', 
        name='Uplink Throughput', 
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND, 
        device_class=SensorDeviceClass.DATA_RATE, 
        state_class=SensorStateClass.MEASUREMENT, 
        value_fn=lambda d: round(float(d.get(DATA_DISH_STATUS, {}).get('uplink_throughput_bps', 0)) / 1000000.0, 2)
    ),
    StarlinkSensorEntityDescription(key='ping_latency', name='Ping Latency', native_unit_of_measurement=UnitOfTime.MILLISECONDS, device_class=SensorDeviceClass.DURATION, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: d.get(DATA_DISH_STATUS, {}).get('pop_ping_latency_ms')),
    StarlinkSensorEntityDescription(key='wifi_clients', name='WiFi Clients', native_unit_of_measurement='devices', state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: len(d.get(DATA_WIFI_CLIENTS, [])), attr_fn=lambda d: {'client_list': [f"{c.get('name') or c.get('mac_address')} ({c.get('ip_address')})" for c in d.get(DATA_WIFI_CLIENTS, [])], 'events': d.get(DATA_USAGE, {}).get('wifi_event_log', [])}),
    StarlinkSensorEntityDescription(key='outage_count_24h', name='Total Outages (24h)', native_unit_of_measurement='events', state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: d.get(DATA_DISH_HISTORY, {}).get('outage_count_24h', 0), attr_fn=lambda d: {'outage_log': d.get(DATA_DISH_HISTORY, {}).get('outage_list_24h', [])}),
    StarlinkSensorEntityDescription(key='searching_count_24h', name='Searching Events (24h)', native_unit_of_measurement='events', state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: d.get(DATA_DISH_HISTORY, {}).get('searching_count_24h', 0)),
    StarlinkSensorEntityDescription(key='booting_count_24h', name='Reboot Events (24h)', native_unit_of_measurement='reboots', state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: d.get(DATA_DISH_HISTORY, {}).get('booting_count_24h', 0)),
    StarlinkSensorEntityDescription(key='obstruction_fraction', name='Obstruction Fraction', native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: round(float(d.get(DATA_DISH_STATUS, {}).get('obstruction_stats', {}).get('fraction_obstructed', 0))*100.0, 2) if d.get(DATA_DISH_STATUS, {}).get('obstruction_stats') else None),
    StarlinkSensorEntityDescription(key='boresight_azimuth', name='Boresight Azimuth', native_unit_of_measurement=DEGREE, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: d.get(DATA_DISH_STATUS, {}).get('boresight_azimuth_deg')),
    StarlinkSensorEntityDescription(key='tilt_angle', name='Tilt Angle', native_unit_of_measurement=DEGREE, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: d.get(DATA_DISH_STATUS, {}).get('alignment_stats', {}).get('tilt_angle_deg')),
    StarlinkSensorEntityDescription(key='p95_latency', name='P95 Latency (History)', native_unit_of_measurement=UnitOfTime.MILLISECONDS, device_class=SensorDeviceClass.DURATION, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: d.get(DATA_DISH_HISTORY, {}).get('p95_latency_ms')),
    StarlinkSensorEntityDescription(key='uptime', name='Uptime', native_unit_of_measurement=UnitOfTime.SECONDS, device_class=SensorDeviceClass.DURATION, value_fn=lambda d: d.get(DATA_DISH_STATUS, {}).get('device_state', {}).get('uptime_s')),
    StarlinkSensorEntityDescription(key='data_usage_total', name='Data Usage (Total)', native_unit_of_measurement=UnitOfInformation.GIGABYTES, device_class=SensorDeviceClass.DATA_SIZE, state_class=SensorStateClass.TOTAL_INCREASING, value_fn=lambda d: d.get(DATA_USAGE, {}).get('total_gb')),
)

async def async_setup_entry(hass: HomeAssistant, entry: Any, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([StarlinkSensor(coordinator, desc) for desc in SENSORS])

class StarlinkSensor(StarlinkEntity, SensorEntity):
    entity_description: StarlinkSensorEntityDescription
    
    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        try: return self.entity_description.attr_fn(self.coordinator.data)
        except: return {}
