from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DATA_DEVICES, DOMAIN
from .entity_base import StarlinkEntity

@dataclass(frozen=True)
class StarlinkBinarySensorEntityDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None] = lambda x: None

BINARY_SENSORS = (
    StarlinkBinarySensorEntityDescription(
        key='connected', 
        name='Connected', 
        device_class=BinarySensorDeviceClass.CONNECTIVITY, 
        value_fn=lambda d: d.get('status', {}).get('state') == 'CONNECTED'
    ),
    StarlinkBinarySensorEntityDescription(
        key='gps_valid', 
        name='GPS Valid', 
        value_fn=lambda d: d.get('status', {}).get('gps_stats', {}).get('gps_valid')
    ),
    StarlinkBinarySensorEntityDescription(
        key='snr_ok', 
        name='SNR Above Noise Floor', 
        value_fn=lambda d: d.get('status', {}).get('is_snr_above_noise_floor')
    ),
    StarlinkBinarySensorEntityDescription(
        key='install_pending', 
        name='Install Pending', 
        value_fn=lambda d: d.get('status', {}).get('ready_states', {}).get('is_install_pending')
    ),
)

async def async_setup_entry(hass: HomeAssistant, entry: Any, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for tid in coordinator.discovered_ids:
        for desc in BINARY_SENSORS:
            val = desc.value_fn(coordinator.data.get(DATA_DEVICES, {}).get(tid, {}))
            if val is not None:
                entities.append(StarlinkBinarySensor(coordinator, desc, tid))
    async_add_entities(entities)

class StarlinkBinarySensor(StarlinkEntity, BinarySensorEntity):
    entity_description: StarlinkBinarySensorEntityDescription
    
    @property
    def is_on(self) -> bool | None:
        dev_data = self.coordinator.data.get(DATA_DEVICES, {}).get(self.target_id, {})
        return self.entity_description.value_fn(dev_data)
