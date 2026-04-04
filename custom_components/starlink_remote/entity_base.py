from __future__ import annotations
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, DATA_DEVICES

class StarlinkEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, description, target_id: str) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self.target_id = target_id
        self._attr_unique_id = f"{target_id}_{description.key}"
        
        dev_data = coordinator.data.get(DATA_DEVICES, {}).get(target_id, {})
        info = dev_data.get('status', {}).get('device_info', {})
        # Use Serial Number (id) or target_id as the device identifier
        serial = info.get('id', target_id)
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, target_id)},
            name=f"Starlink {serial}",
            manufacturer='SpaceX',
            model=info.get('hardware_version', 'Starlink Device'),
            sw_version=info.get('software_version'),
        )
