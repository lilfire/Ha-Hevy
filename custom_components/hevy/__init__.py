"""The Hevy integration."""

from __future__ import annotations

from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import HevyClient
from .const import DOMAIN
from .coordinator import (
    HevyConfigEntry,
    HevyCoordinator,
    exercise_device_id,
    routine_device_id,
    store_for,
)
from .services import async_setup_services

PLATFORMS: list[Platform] = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Hevy services."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HevyConfigEntry) -> bool:
    """Set up Hevy from a config entry."""
    client = HevyClient(async_get_clientsession(hass), entry.data[CONF_API_KEY])
    coordinator = HevyCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: HevyConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HevyConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: HevyConfigEntry) -> None:
    """Delete the cached workout history."""
    await store_for(hass, entry.entry_id).async_remove()


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: HevyConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing exercise/routine devices that no longer exist in Hevy."""
    data = entry.runtime_data.data
    current = {str(entry.unique_id)}
    current |= {exercise_device_id(entry.unique_id, t) for t in data.exercises}
    current |= {routine_device_id(entry.unique_id, r) for r in data.routine_stats}
    return not any(
        domain == DOMAIN and identifier in current
        for domain, identifier in device.identifiers
    )
