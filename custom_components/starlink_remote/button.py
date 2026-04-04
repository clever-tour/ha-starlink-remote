"""Button platform for Starlink Remote."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DATA_DEVICES, DOMAIN
from .entity_base import StarlinkEntity

@dataclass(frozen=True, kw_only=True)
class StarlinkButtonEntityDescription(ButtonEntityDescription):
    """Class describing Starlink button entities."""
    request_field: str = ""
    request_factory: Callable[[], Any] = lambda: None
    dev_types: list[str] = None

def get_reboot_request():
    """Create a reboot request."""
    from .spacex.api.device.device_pb2 import RebootRequest
    return RebootRequest()

def get_stow_request():
    """Create a stow request."""
    from .spacex.api.device.dish_pb2 import DishStowRequest
    return DishStowRequest(unstow=False)

def get_unstow_request():
    """Create an unstow request."""
    from .spacex.api.device.dish_pb2 import DishStowRequest
    return DishStowRequest(unstow=True)

BUTTONS = (
    StarlinkButtonEntityDescription(
        key="reboot",
        name="Reboot",
        request_field="reboot",
        request_factory=get_reboot_request,
        dev_types=["dish", "router"],
        icon="mdi:restart"
    ),
    StarlinkButtonEntityDescription(
        key="stow",
        name="Stow",
        request_field="dish_stow",
        request_factory=get_stow_request,
        dev_types=["dish"],
        icon="mdi:arrow-down-box"
    ),
    StarlinkButtonEntityDescription(
        key="unstow",
        name="Unstow",
        request_field="dish_stow",
        request_factory=get_unstow_request,
        dev_types=["dish"],
        icon="mdi:arrow-up-box"
    ),
)

async def async_setup_entry(hass: HomeAssistant, entry: Any, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the Starlink button platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for tid, dev_data in coordinator.data.get(DATA_DEVICES, {}).items():
        dev_type = dev_data["type"]
        for desc in BUTTONS:
            if dev_type in desc.dev_types:
                entities.append(StarlinkDeviceButton(coordinator, desc, tid))
    async_add_entities(entities)

class StarlinkDeviceButton(StarlinkEntity, ButtonEntity):
    """Representation of a Starlink button."""
    entity_description: StarlinkButtonEntityDescription
    
    async def async_press(self) -> None:
        """Handle the button press."""
        req_data = self.entity_description.request_factory()
        await self.coordinator.async_send_command(
            self.target_id, 
            self.entity_description.request_field, 
            req_data
        )
