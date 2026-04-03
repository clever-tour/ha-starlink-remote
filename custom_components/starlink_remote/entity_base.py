from __future__ import annotations
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, DATA_DISH_STATUS

class StarlinkEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, description) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator._router_id}_{description.key}"
        
        info = coordinator.data.get(DATA_DISH_STATUS, {}).get('device_info', {})
        # Use Serial Number (id) as the device name
        serial = info.get('id', coordinator._router_id)
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator._router_id)},
            name=f"Starlink {serial}",
            manufacturer='SpaceX',
            model=info.get('hardware_version', 'Starlink Device'),
            sw_version=info.get('software_version'),
        )
