"""Sensor platform for Starlink Remote."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Callable
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import UnitOfDataRate, UnitOfTime, UnitOfInformation, PERCENTAGE, DEGREE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from .const import DATA_DEVICES, DATA_USAGE, DOMAIN
from .entity_base import StarlinkEntity

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class StarlinkSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], StateType] = lambda x: None
    attr_fn: Callable[[dict[str, Any]], dict[str, Any]] = lambda x: {}
    dev_types: list[str] = None

SENSOR_DESCRIPTIONS = (
    # Global
    StarlinkSensorEntityDescription(
        key='data_usage_total', name='Data Usage (Total)', 
        native_unit_of_measurement=UnitOfInformation.GIGABYTES, 
        device_class=SensorDeviceClass.DATA_SIZE, 
        state_class=SensorStateClass.TOTAL_INCREASING, 
        value_fn=lambda d: d.get(DATA_USAGE, {}).get('total_gb'),
        dev_types=['global']
    ),
    # Common
    StarlinkSensorEntityDescription(
        key='state', name='State', 
        value_fn=lambda d: d.get('status', {}).get('state'),
        dev_types=['dish', 'router']
    ),
    StarlinkSensorEntityDescription(
        key='uptime', name='Uptime', 
        native_unit_of_measurement=UnitOfTime.SECONDS, 
        device_class=SensorDeviceClass.DURATION, 
        value_fn=lambda d: d.get('status', {}).get('device_state', {}).get('uptime_s'),
        dev_types=['dish', 'router']
    ),
    # Dish Specific
    StarlinkSensorEntityDescription(
        key='downlink_throughput', name='Downlink Throughput', 
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND, 
        device_class=SensorDeviceClass.DATA_RATE, 
        state_class=SensorStateClass.MEASUREMENT, 
        value_fn=lambda d: round(float(d.get('status', {}).get('downlink_throughput_bps', 0)) / 1e6, 2),
        dev_types=['dish']
    ),
    StarlinkSensorEntityDescription(
        key='uplink_throughput', name='Uplink Throughput', 
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND, 
        device_class=SensorDeviceClass.DATA_RATE, 
        state_class=SensorStateClass.MEASUREMENT, 
        value_fn=lambda d: round(float(d.get('status', {}).get('uplink_throughput_bps', 0)) / 1e6, 2),
        dev_types=['dish']
    ),
    StarlinkSensorEntityDescription(
        key='ping_latency', name='Ping Latency', 
        native_unit_of_measurement=UnitOfTime.MILLISECONDS, 
        device_class=SensorDeviceClass.DURATION, 
        state_class=SensorStateClass.MEASUREMENT, 
        value_fn=lambda d: d.get('status', {}).get('pop_ping_latency_ms'),
        dev_types=['dish']
    ),
    StarlinkSensorEntityDescription(
        key='obstruction_fraction', name='Obstruction Fraction', 
        native_unit_of_measurement=PERCENTAGE, 
        state_class=SensorStateClass.MEASUREMENT, 
        value_fn=lambda d: round(float(d.get('status', {}).get('obstruction_stats', {}).get('fraction_obstructed', 0))*100.0, 2) if d.get('status', {}).get('obstruction_stats') else None,
        dev_types=['dish']
    ),
    StarlinkSensorEntityDescription(
        key='boresight_azimuth', name='Boresight Azimuth', 
        native_unit_of_measurement=DEGREE, 
        state_class=SensorStateClass.MEASUREMENT, 
        value_fn=lambda d: d.get('status', {}).get('boresight_azimuth_deg'),
        dev_types=['dish']
    ),
    StarlinkSensorEntityDescription(
        key='tilt_angle', name='Tilt Angle', 
        native_unit_of_measurement=DEGREE, 
        state_class=SensorStateClass.MEASUREMENT, 
        value_fn=lambda d: d.get('status', {}).get('alignment_stats', {}).get('tilt_angle_deg'),
        dev_types=['dish']
    ),
    # DISH EVENT LOGS
    StarlinkSensorEntityDescription(
        key='bootcount', name='Boot Count', 
        state_class=SensorStateClass.TOTAL_INCREASING, 
        value_fn=lambda d: d.get('status', {}).get('device_info', {}).get('bootcount'),
        dev_types=['dish']
    ),
    StarlinkSensorEntityDescription(
        key='searching_events', name='Searching Events', 
        state_class=SensorStateClass.MEASUREMENT, 
        value_fn=lambda d: len([o for o in d.get('history', {}).get('outages', []) if o.get('cause') == 'SEARCHING']),
        attr_fn=lambda d: {'outages': [o for o in d.get('history', {}).get('outages', []) if o.get('cause') == 'SEARCHING']},
        dev_types=['dish']
    ),
    StarlinkSensorEntityDescription(
        key='total_outages', name='Total Outages', 
        state_class=SensorStateClass.MEASUREMENT, 
        value_fn=lambda d: len(d.get('history', {}).get('outages', [])),
        attr_fn=lambda d: {'outages': d.get('history', {}).get('outages', [])},
        dev_types=['dish']
    ),
    # Router Specific
    StarlinkSensorEntityDescription(
        key='wifi_clients', name='WiFi Clients', 
        native_unit_of_measurement='devices', 
        state_class=SensorStateClass.MEASUREMENT, 
        value_fn=lambda d: len(d.get('status', {}).get('clients', [])),
        attr_fn=lambda d: {
            'client_list': [f"{c.get('name') or c.get('mac_address')} ({c.get('ip_address')})" for c in d.get('status', {}).get('clients', [])],
            'ping_history': d.get('history', {}).get('ping_latency_ms', [])[-10:]
        },
        dev_types=['router']
    ),
)

async def async_setup_entry(hass: HomeAssistant, entry: Any, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    
    dish_id = next((tid for tid, d in coordinator.data.get(DATA_DEVICES, {}).items() if d['type'] == 'dish'), None)
    
    for tid, dev_data in coordinator.data.get(DATA_DEVICES, {}).items():
        dev_type = dev_data['type']
        for desc in SENSOR_DESCRIPTIONS:
            if dev_type in desc.dev_types:
                entities.append(StarlinkDeviceSensor(coordinator, desc, tid))
            
            if 'global' in desc.dev_types:
                if (dev_type == 'dish') or (not dish_id and dev_type == 'router'):
                    entities.append(StarlinkDeviceSensor(coordinator, desc, tid))
                
    async_add_entities(entities)

class StarlinkDeviceSensor(StarlinkEntity, SensorEntity):
    entity_description: StarlinkSensorEntityDescription
    
    @property
    def native_value(self) -> StateType:
        if 'global' in self.entity_description.dev_types:
            val = self.entity_description.value_fn(self.coordinator.data)
            if val is not None: return val
            
        dev_data = self.coordinator.data.get(DATA_DEVICES, {}).get(self.target_id, {})
        return self.entity_description.value_fn(dev_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        try:
            dev_data = self.coordinator.data.get(DATA_DEVICES, {}).get(self.target_id, {})
            return self.entity_description.attr_fn(dev_data)
        except: return {}
