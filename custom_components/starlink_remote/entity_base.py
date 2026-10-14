"""Base entity for Starlink Remote."""
from __future__ import annotations
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, DATA_DEVICES

#: Deep link shown on every device page, so the user can reach the account the
#: telemetry belongs to from Home Assistant.
ACCOUNT_URL = "https://www.starlink.com/account/home"


class StarlinkEntity(CoordinatorEntity):
    """Base class for all Starlink entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, description, target_id: str) -> None:
        """Initialize the entity.

        Both the unique id and the device identifier start with the config
        entry id: several entries (several Starlink accounts, or the same
        account added twice) may describe the very same dish or router, and
        without that prefix the second entry's entities would be rejected as
        duplicates of the first entry's instead of being created beside them.
        """
        super().__init__(coordinator)
        self.entity_description = description
        self.target_id = target_id
        entry_id = coordinator.entry_id
        self._attr_unique_id = f"{entry_id}_{target_id}_{description.key}"

        # Device identity comes from the polled hardware inventory. It is read
        # once at construction and is stable afterwards, so a device that is
        # temporarily unreachable keeps its registry entry instead of turning
        # into a new device.
        dev_data = coordinator.data.get(DATA_DEVICES, {}).get(target_id, {})
        dev_type = dev_data.get("type", "device").capitalize()
        info = dev_data.get("status", {}).get("device_info", {})
        serial = str(info.get("id") or target_id)
        short_serial = serial[-8:] if len(serial) > 8 else serial

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{target_id}")},
            name=f"Starlink {dev_type} ({short_serial})",
            manufacturer="SpaceX",
            model=info.get("hardware_version") or f"Starlink {dev_type}",
            sw_version=info.get("software_version"),
            configuration_url=ACCOUNT_URL,
        )
