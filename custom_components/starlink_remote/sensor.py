from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Callable
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import UnitOfDataRate, UnitOfTime, UnitOfInformation, PERCENTAGE, DEGREE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from .const import DATA_DEVICES, DATA_WIFI_CLIENTS, DATA_USAGE, DOMAIN
from .entity_base import StarlinkEntity

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class StarlinkSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], StateType] = lambda x: None
    attr_fn: Callable[[dict[str, Any]], dict[str, Any]] = lambda x: {}

# Global Account Sensors
GLOBAL_SENSORS = (
    StarlinkSensorEntityDescription(
        key='data_usage_total', 
        name='Data Usage (Total)', 
        native_unit_of_measurement=UnitOfInformation.GIGABYTES, 
        device_class=SensorDeviceClass.DATA_SIZE, 
        state_class=SensorStateClass.TOTAL_INCREASING, 
        value_fn=lambda d: d.get(DATA_USAGE, {}).get('total_gb')
    ),
    StarlinkSensorEntityDescription(
        key='wifi_event_log', 
        name='WiFi Event Log', 
        value_fn=lambda d: len(d.get(DATA_USAGE, {}).get('wifi_event_log', [])),
        attr_fn=lambda d: {'events': d.get(DATA_USAGE, {}).get('wifi_event_log', [])}
    ),
)

# Per-Device Sensors
DEVICE_SENSORS = (
    StarlinkSensorEntityDescription(key='state', name='State', value_fn=lambda d: d.get('status', {}).get('state')),
    StarlinkSensorEntityDescription(
        key='downlink_throughput', 
        name='Downlink Throughput', 
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND, 
        device_class=SensorDeviceClass.DATA_RATE, 
        state_class=SensorStateClass.MEASUREMENT, 
        value_fn=lambda d: round(float(d.get('status', {}).get('downlink_throughput_bps', 0)) / 1000000.0, 2)
    ),
    StarlinkSensorEntityDescription(
        key='uplink_throughput', 
        name='Uplink Throughput', 
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND, 
        device_class=SensorDeviceClass.DATA_RATE, 
        state_class=SensorStateClass.MEASUREMENT, 
        value_fn=lambda d: round(float(d.get('status', {}).get('uplink_throughput_bps', 0)) / 1000000.0, 2)
    ),
    StarlinkSensorEntityDescription(key='ping_latency', name='Ping Latency', native_unit_of_measurement=UnitOfTime.MILLISECONDS, device_class=SensorDeviceClass.DURATION, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: d.get('status', {}).get('pop_ping_latency_ms')),
    StarlinkSensorEntityDescription(key='wifi_clients', name='WiFi Clients', native_unit_of_measurement='devices', state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: len(d.get('wifi_clients', [])), attr_fn=lambda d: {'client_list': [f"{c.get('name') or c.get('mac_address')} ({c.get('ip_address')})" for c in d.get('wifi_clients', [])]}),
    StarlinkSensorEntityDescription(key='outage_count_24h', name='Total Outages (24h)', native_unit_of_measurement='events', state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: d.get('history', {}).get('outage_count_24h', 0), attr_fn=lambda d: {'outage_log': d.get('history', {}).get('outage_list_24h', [])}),
    StarlinkSensorEntityDescription(key='searching_count_24h', name='Searching Events (24h)', native_unit_of_measurement='events', state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: d.get('history', {}).get('searching_count_24h', 0)),
    StarlinkSensorEntityDescription(key='booting_count_24h', name='Reboot Events (24h)', native_unit_of_measurement='reboots', state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: d.get('history', {}).get('booting_count_24h', 0)),
    StarlinkSensorEntityDescription(key='obstruction_fraction', name='Obstruction Fraction', native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: round(float(d.get('status', {}).get('obstruction_stats', {}).get('fraction_obstructed', 0))*100.0, 2) if d.get('status', {}).get('obstruction_stats') else None),
    StarlinkSensorEntityDescription(key='boresight_azimuth', name='Boresight Azimuth', native_unit_of_measurement=DEGREE, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: d.get('status', {}).get('boresight_azimuth_deg')),
    StarlinkSensorEntityDescription(key='tilt_angle', name='Tilt Angle', native_unit_of_measurement=DEGREE, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: d.get('status', {}).get('alignment_stats', {}).get('tilt_angle_deg')),
    StarlinkSensorEntityDescription(key='p95_latency', name='P95 Latency (History)', native_unit_of_measurement=UnitOfTime.MILLISECONDS, device_class=SensorDeviceClass.DURATION, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: d.get('history', {}).get('p95_latency_ms')),
    StarlinkSensorEntityDescription(key='uptime', name='Uptime', native_unit_of_measurement=UnitOfTime.SECONDS, device_class=SensorDeviceClass.DURATION, value_fn=lambda d: d.get('status', {}).get('device_state', {}).get('uptime_s')),
)

async def async_setup_entry(hass: HomeAssistant, entry: Any, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    
    # Global sensors linked to the first discovered ID as a representative device
    first_id = list(coordinator.discovered_ids)[0] if coordinator.discovered_ids else "Account"
    for desc in GLOBAL_SENSORS:
        entities.append(StarlinkGlobalSensor(coordinator, desc, first_id))
        
    # Per-device sensors
    for tid in coordinator.discovered_ids:
        for desc in DEVICE_SENSORS:
            # Only add if data exists for this sensor on this device
            val = desc.value_fn(coordinator.data.get(DATA_DEVICES, {}).get(tid, {}))
            if val is not None:
                entities.append(StarlinkDeviceSensor(coordinator, desc, tid))
                
    async_add_entities(entities)

class StarlinkDeviceSensor(StarlinkEntity, SensorEntity):
    """Sensor for a specific hardware device."""
    entity_description: StarlinkSensorEntityDescription
    
    @property
    def native_value(self) -> StateType:
        dev_data = self.coordinator.data.get(DATA_DEVICES, {}).get(self.target_id, {})
        return self.entity_description.value_fn(dev_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        try:
            dev_data = self.coordinator.data.get(DATA_DEVICES, {}).get(self.target_id, {})
            return self.entity_description.attr_fn(dev_data)
        except: return {}

class StarlinkGlobalSensor(StarlinkEntity, SensorEntity):
    """Sensor for account-wide data."""
    entity_description: StarlinkSensorEntityDescription
    
    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        try: return self.entity_description.attr_fn(self.coordinator.data)
        except: return {}
