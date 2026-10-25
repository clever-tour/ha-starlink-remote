"""Button platform for Starlink Remote.

Only the restart command is exposed. Stow/unstow and every other state-changing
command were removed: the binding is read-only against the Starlink API except
for this one action, which the user explicitly keeps available.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_DEVICES, DOMAIN
from .entity_base import StarlinkEntity


@dataclass(frozen=True, kw_only=True)
class StarlinkButtonEntityDescription(ButtonEntityDescription):
    """Describe a Starlink button."""

    request_field: str = ""
    request_factory: Callable[[], Any] = lambda: None
    dev_types: tuple[str, ...] = ()


def get_reboot_request() -> Any:
    """Return a restart request."""
    from .spacex.api.device.device_pb2 import RebootRequest

    return RebootRequest()


BUTTONS = (
    StarlinkButtonEntityDescription(
        key="reboot",
        translation_key="reboot",
        request_field="reboot",
        request_factory=get_reboot_request,
        dev_types=("dish", "router"),
        icon="mdi:restart",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: Any, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the button for every device the coordinator discovered."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[StarlinkDeviceButton] = []
    for target_id, device in coordinator.data.get(DATA_DEVICES, {}).items():
        for description in BUTTONS:
            if device.get("type") in description.dev_types:
                entities.append(StarlinkDeviceButton(coordinator, description, target_id))
    async_add_entities(entities)


class StarlinkDeviceButton(StarlinkEntity, ButtonEntity):
    """A command button of one Starlink device."""

    entity_description: StarlinkButtonEntityDescription

    async def async_press(self) -> None:
        """Send the command to this device."""
        request = self.entity_description.request_factory()
        await self.coordinator.async_send_command(
            self.target_id, self.entity_description.request_field, request
        )
