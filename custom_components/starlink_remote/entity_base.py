"""Base entity for Starlink Remote."""
from __future__ import annotations
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, DATA_DEVICES

class StarlinkEntity(CoordinatorEntity):
    """Base class for all Starlink entities."""
    _attr_has_entity_name = True

    def __init__(self, coordinator, description, target_id: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self.target_id = target_id
        self._attr_unique_id = f"{target_id}_{description.key}"
        
        dev_data = coordinator.data.get(DATA_DEVICES, {}).get(target_id, {})
        dev_type = dev_data.get('type', 'device').capitalize()
        info = dev_data.get('status', {}).get('device_info', {})
        serial = info.get('id', target_id)
        
        # Nicer naming: "Starlink Dish (Serial)" or "Starlink Router (Serial)"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, target_id)},
            name=f"Starlink {dev_type} ({serial[-8:] if len(serial) > 8 else serial})",
            manufacturer='SpaceX',
            model=info.get('hardware_version', f'Starlink {dev_type}'),
            sw_version=info.get('software_version'),
        )
