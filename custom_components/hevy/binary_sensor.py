"""Binary sensors for Hevy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import HevyConfigEntry, HevyCoordinator, HevyData
from .entity import HevyEntity
from .stats import parse_time, start_of_week

PARALLEL_UPDATES = 0


def _worked_out_today(data: HevyData) -> bool:
    today = dt_util.as_local(dt_util.utcnow()).date()
    latest = data.latest_workout
    started = parse_time(latest.get("start_time")) if latest else None
    return started is not None and dt_util.as_local(started).date() == today


def _worked_out_this_week(data: HevyData) -> bool:
    latest = data.latest_workout
    started = parse_time(latest.get("start_time")) if latest else None
    return started is not None and started >= start_of_week()


@dataclass(frozen=True, kw_only=True)
class HevyBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Hevy binary sensor."""

    is_on_fn: Callable[[HevyData], bool]


BINARY_SENSORS: tuple[HevyBinarySensorEntityDescription, ...] = (
    HevyBinarySensorEntityDescription(
        key="worked_out_today",
        translation_key="worked_out_today",
        is_on_fn=_worked_out_today,
    ),
    HevyBinarySensorEntityDescription(
        key="worked_out_this_week",
        translation_key="worked_out_this_week",
        is_on_fn=_worked_out_this_week,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HevyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hevy binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        HevyBinarySensor(coordinator, description) for description in BINARY_SENSORS
    )


class HevyBinarySensor(HevyEntity, BinarySensorEntity):
    """A Hevy binary sensor."""

    entity_description: HevyBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: HevyCoordinator,
        description: HevyBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.entity_description.is_on_fn(self.coordinator.data)
