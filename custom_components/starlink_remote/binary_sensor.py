"""Binary sensor platform for Starlink Remote."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_DEVICES, DOMAIN
from .entity_base import StarlinkEntity


@dataclass(frozen=True, kw_only=True)
class StarlinkBinarySensorEntityDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None] = lambda x: None
    dev_types: tuple[str, ...] = ()

BINARY_SENSORS = (
    StarlinkBinarySensorEntityDescription(
        key='connected',
        translation_key='connected',
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda d: d.get('status', {}).get('state') == 'CONNECTED',
        dev_types=('dish', 'router')
    ),
    StarlinkBinarySensorEntityDescription(
        key='gps_valid',
        translation_key='gps_valid',
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get('status', {}).get('gps_stats', {}).get('gps_valid'),
        dev_types=('dish',)
    ),
    StarlinkBinarySensorEntityDescription(
        key='snr_ok',
        translation_key='snr_ok',
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get('status', {}).get('is_snr_above_noise_floor'),
        dev_types=('dish',)
    ),
)

async def async_setup_entry(hass: HomeAssistant, entry: Any, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for tid, dev_data in coordinator.data.get(DATA_DEVICES, {}).items():
        dev_type = dev_data['type']
        for desc in BINARY_SENSORS:
            if dev_type in desc.dev_types:
                entities.append(StarlinkBinarySensor(coordinator, desc, tid))
    async_add_entities(entities)

class StarlinkBinarySensor(StarlinkEntity, BinarySensorEntity):
    entity_description: StarlinkBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        dev_data = self.coordinator.data.get(DATA_DEVICES, {}).get(self.target_id, {})
        return self.entity_description.value_fn(dev_data)
