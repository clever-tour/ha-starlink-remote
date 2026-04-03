from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DATA_DISH_STATUS, DOMAIN
from .entity_base import StarlinkEntity
@dataclass(frozen=True)
class StarlinkBinarySensorEntityDescription(BinarySensorEntityDescription):
    is_on_fn: Callable[[dict[str, Any]], bool] = lambda x: False
BINARY_SENSORS = (
    StarlinkBinarySensorEntityDescription(key='connected', name='Connected', device_class=BinarySensorDeviceClass.CONNECTIVITY, is_on_fn=lambda d: d.get(DATA_DISH_STATUS, {}).get('state') == 'CONNECTED' or d.get(DATA_DISH_STATUS, {}).get('state') is not None),
    StarlinkBinarySensorEntityDescription(key='gps_valid', name='GPS Valid', is_on_fn=lambda d: d.get(DATA_DISH_STATUS, {}).get('gps_stats', {}).get('gps_valid') is True),
    StarlinkBinarySensorEntityDescription(key='snr_ok', name='SNR Above Noise Floor', is_on_fn=lambda d: d.get(DATA_DISH_STATUS, {}).get('is_snr_above_noise_floor') is True),
    StarlinkBinarySensorEntityDescription(key='install_pending', name='Install Pending', is_on_fn=lambda d: d.get(DATA_DISH_STATUS, {}).get('alerts', {}).get('install_pending') is True),
)
async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([StarlinkBinarySensor(coordinator, desc) for desc in BINARY_SENSORS])
class StarlinkBinarySensor(StarlinkEntity, BinarySensorEntity):
    entity_description: StarlinkBinarySensorEntityDescription
    @property
    def is_on(self) -> bool: return self.entity_description.is_on_fn(self.coordinator.data)
