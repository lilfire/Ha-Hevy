"""Base entities for Hevy."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HevyCoordinator, exercise_device_id, routine_device_id
from .stats import ExerciseStats, RoutineStats


class HevyEntity(CoordinatorEntity[HevyCoordinator]):
    """An entity on the Hevy account device."""

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


class HevyExerciseEntity(CoordinatorEntity[HevyCoordinator]):
    """An entity on an exercise device."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: HevyCoordinator, template_id: str, key: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.template_id = template_id
        unique_id = coordinator.config_entry.unique_id
        stats = coordinator.data.exercises[template_id]
        muscle = stats.template.get("primary_muscle_group")
        self._attr_unique_id = f"{exercise_device_id(unique_id, template_id)}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, exercise_device_id(unique_id, template_id))},
            name=stats.title,
            manufacturer="Hevy",
            model=muscle.replace("_", " ").capitalize() if muscle else "Exercise",
            model_id=template_id,
            entry_type=DeviceEntryType.SERVICE,
            via_device=(DOMAIN, str(unique_id)),
        )

    @property
    def stats(self) -> ExerciseStats | None:
        """Current statistics for the exercise."""
        return self.coordinator.data.exercises.get(self.template_id)

    @property
    def available(self) -> bool:
        """Available while the exercise exists in the history."""
        return super().available and self.stats is not None


class HevyRoutineEntity(CoordinatorEntity[HevyCoordinator]):
    """An entity on a routine device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HevyCoordinator, routine_id: str, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.routine_id = routine_id
        unique_id = coordinator.config_entry.unique_id
        stats = coordinator.data.routine_stats[routine_id]
        self._attr_unique_id = f"{routine_device_id(unique_id, routine_id)}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, routine_device_id(unique_id, routine_id))},
            name=stats.title,
            manufacturer="Hevy",
            model=f"Routine – {stats.folder_name}" if stats.folder_name else "Routine",
            entry_type=DeviceEntryType.SERVICE,
            via_device=(DOMAIN, str(unique_id)),
        )

    @property
    def stats(self) -> RoutineStats | None:
        """Current statistics for the routine."""
        return self.coordinator.data.routine_stats.get(self.routine_id)

    @property
    def available(self) -> bool:
        """Available while the routine exists in Hevy."""
        return super().available and self.stats is not None
