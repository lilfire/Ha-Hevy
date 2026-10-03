"""Base entity for Hevy."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HevyCoordinator


class HevyEntity(CoordinatorEntity[HevyCoordinator]):
    """Common base for Hevy entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HevyCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        user = coordinator.data.user if coordinator.data else {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.unique_id))},
            name=f"Hevy {user.get('name') or entry.title}",
            manufacturer="Hevy",
            model="Hevy account",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=user.get("url") or "https://hevy.com",
        )
