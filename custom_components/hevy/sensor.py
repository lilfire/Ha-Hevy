"""Sensors for Hevy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .api import JSON
from .coordinator import HevyConfigEntry, HevyCoordinator, HevyData
from .entity import HevyEntity, HevyExerciseEntity, HevyRoutineEntity
from .stats import (
    ExerciseStats,
    RoutineStats,
    parse_time,
    workout_duration_minutes,
    workout_set_count,
    workout_volume_kg,
)

PARALLEL_UPDATES = 0


def _workouts_since(data: HevyData, start: datetime) -> list[JSON]:
    return [
        w
        for w in data.workouts
        if (t := parse_time(w.get("start_time"))) is not None and t >= start
    ]


def _start_of_week() -> datetime:
    today = dt_util.start_of_local_day()
    return dt_util.as_utc(today - timedelta(days=today.weekday()))


def _days_ago(days: int) -> datetime:
    return dt_util.utcnow() - timedelta(days=days)


def _latest(data: HevyData, fn: Callable[[JSON], Any]) -> Any:
    workout = data.latest_workout
    return fn(workout) if workout else None


def _latest_workout_attrs(data: HevyData) -> dict[str, Any]:
    workout = data.latest_workout
    if not workout:
        return {}
    return {
        "workout_id": workout.get("id"),
        "title": workout.get("title"),
        "description": workout.get("description"),
        "routine_id": workout.get("routine_id"),
        "start_time": workout.get("start_time"),
        "end_time": workout.get("end_time"),
        "duration_minutes": workout_duration_minutes(workout),
        "volume_kg": workout_volume_kg(workout),
        "set_count": workout_set_count(workout),
        "exercises": [
            {
                "title": ex.get("title"),
                "exercise_template_id": ex.get("exercise_template_id"),
                "sets": len(ex.get("sets") or []),
            }
            for ex in workout.get("exercises") or []
        ],
    }


def _measurement(field: str) -> Callable[[HevyData], StateType]:
    def _value(data: HevyData) -> StateType:
        if data.body_measurement is None:
            return None
        return data.body_measurement.get(field)

    return _value


def _measurement_date(data: HevyData) -> date | None:
    if data.body_measurement is None:
        return None
    return dt_util.parse_date(data.body_measurement.get("date") or "")


@dataclass(frozen=True, kw_only=True)
class HevySensorEntityDescription(SensorEntityDescription):
    """Describes a Hevy sensor."""

    value_fn: Callable[[HevyData], StateType | date | datetime]
    attrs_fn: Callable[[HevyData], dict[str, Any]] | None = None


SENSORS: tuple[HevySensorEntityDescription, ...] = (
    HevySensorEntityDescription(
        key="workout_count",
        translation_key="workout_count",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: d.workout_count,
    ),
    HevySensorEntityDescription(
        key="last_workout",
        translation_key="last_workout",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _latest(d, lambda w: parse_time(w.get("start_time"))),
        attrs_fn=_latest_workout_attrs,
    ),
    HevySensorEntityDescription(
        key="last_workout_title",
        translation_key="last_workout_title",
        value_fn=lambda d: _latest(d, lambda w: w.get("title")),
    ),
    HevySensorEntityDescription(
        key="last_workout_duration",
        translation_key="last_workout_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=lambda d: _latest(d, workout_duration_minutes),
    ),
    HevySensorEntityDescription(
        key="last_workout_volume",
        translation_key="last_workout_volume",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        suggested_display_precision=0,
        value_fn=lambda d: _latest(d, workout_volume_kg),
    ),
    HevySensorEntityDescription(
        key="last_workout_sets",
        translation_key="last_workout_sets",
        value_fn=lambda d: _latest(d, workout_set_count),
    ),
    HevySensorEntityDescription(
        key="workouts_this_week",
        translation_key="workouts_this_week",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(_workouts_since(d, _start_of_week())),
    ),
    HevySensorEntityDescription(
        key="volume_this_week",
        translation_key="volume_this_week",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: round(
            sum(workout_volume_kg(w) for w in _workouts_since(d, _start_of_week())), 2
        ),
    ),
    HevySensorEntityDescription(
        key="workouts_last_7_days",
        translation_key="workouts_last_7_days",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(_workouts_since(d, _days_ago(7))),
    ),
    HevySensorEntityDescription(
        key="workouts_last_30_days",
        translation_key="workouts_last_30_days",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(_workouts_since(d, _days_ago(30))),
    ),
    HevySensorEntityDescription(
        key="routines",
        translation_key="routines",
        value_fn=lambda d: len(d.routines),
        attrs_fn=lambda d: {
            "routines": [
                {
                    "id": r.get("id"),
                    "title": r.get("title"),
                    "folder_id": r.get("folder_id"),
                }
                for r in d.routines
            ]
        },
    ),
    HevySensorEntityDescription(
        key="routine_folders",
        translation_key="routine_folders",
        value_fn=lambda d: len(d.routine_folders),
        attrs_fn=lambda d: {
            "routine_folders": [
                {"id": f.get("id"), "title": f.get("title")} for f in d.routine_folders
            ]
        },
    ),
    HevySensorEntityDescription(
        key="body_measurement_date",
        translation_key="body_measurement_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=_measurement_date,
    ),
    HevySensorEntityDescription(
        key="weight",
        translation_key="weight",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_measurement("weight_kg"),
    ),
    HevySensorEntityDescription(
        key="lean_mass",
        translation_key="lean_mass",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=_measurement("lean_mass_kg"),
    ),
    HevySensorEntityDescription(
        key="fat_percent",
        translation_key="fat_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_measurement("fat_percent"),
    ),
    *(
        HevySensorEntityDescription(
            key=field.removesuffix("_cm"),
            translation_key=field.removesuffix("_cm"),
            device_class=SensorDeviceClass.DISTANCE,
            native_unit_of_measurement=UnitOfLength.CENTIMETERS,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            entity_registry_enabled_default=False,
            value_fn=_measurement(field),
        )
        for field in (
            "neck_cm",
            "shoulder_cm",
            "chest_cm",
            "left_bicep_cm",
            "right_bicep_cm",
            "left_forearm_cm",
            "right_forearm_cm",
            "abdomen",
            "waist",
            "hips",
            "left_thigh",
            "right_thigh",
            "left_calf",
            "right_calf",
        )
    ),
)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _best_set_text(stats: ExerciseStats) -> str | None:
    best = stats.best_set
    if best is None:
        return None
    return f"{best.weight_kg:g} kg × {best.reps}"


def _best_set_attrs(stats: ExerciseStats) -> dict[str, Any]:
    best = stats.best_set
    if best is None:
        return {}
    return {
        "weight_kg": best.weight_kg,
        "reps": best.reps,
        "estimated_1rm_kg": best.estimated_1rm,
        "workout_id": best.workout_id,
        "date": _iso(best.date),
    }


def _exercise_attrs(stats: ExerciseStats) -> dict[str, Any]:
    template = stats.template
    return {
        "exercise_template_id": stats.exercise_template_id,
        "exercise_type": template.get("type"),
        "primary_muscle_group": template.get("primary_muscle_group"),
        "secondary_muscle_groups": template.get("secondary_muscle_groups"),
        "is_custom": template.get("is_custom"),
        "last_workout_id": stats.last_workout_id,
        "last_workout_title": stats.last_workout_title,
    }


@dataclass(frozen=True, kw_only=True)
class HevyExerciseSensorEntityDescription(SensorEntityDescription):
    """Describes a per-exercise sensor."""

    value_fn: Callable[[ExerciseStats], StateType | datetime]
    exists_fn: Callable[[ExerciseStats], bool] = lambda _: True
    attrs_fn: Callable[[ExerciseStats], dict[str, Any]] | None = None


def _weight(**kwargs: Any) -> dict[str, Any]:
    return {
        "device_class": SensorDeviceClass.WEIGHT,
        "native_unit_of_measurement": UnitOfMass.KILOGRAMS,
        "suggested_display_precision": 1,
        **kwargs,
    }


EXERCISE_SENSORS: tuple[HevyExerciseSensorEntityDescription, ...] = (
    # Strength
    HevyExerciseSensorEntityDescription(
        key="max_weight",
        translation_key="exercise_max_weight",
        **_weight(state_class=SensorStateClass.MEASUREMENT),
        exists_fn=lambda s: s.has_weight,
        value_fn=lambda s: s.max_weight_kg,
        attrs_fn=lambda s: {"date": _iso(s.max_weight_date)},
    ),
    HevyExerciseSensorEntityDescription(
        key="estimated_1rm",
        translation_key="exercise_estimated_1rm",
        **_weight(state_class=SensorStateClass.MEASUREMENT),
        exists_fn=lambda s: s.best_set is not None,
        value_fn=lambda s: s.best_set.estimated_1rm if s.best_set else None,
        attrs_fn=_best_set_attrs,
    ),
    HevyExerciseSensorEntityDescription(
        key="best_set",
        translation_key="exercise_best_set",
        entity_registry_enabled_default=False,
        exists_fn=lambda s: s.best_set is not None,
        value_fn=_best_set_text,
        attrs_fn=_best_set_attrs,
    ),
    HevyExerciseSensorEntityDescription(
        key="last_volume",
        translation_key="exercise_last_volume",
        **_weight(state_class=SensorStateClass.MEASUREMENT),
        exists_fn=lambda s: s.has_weight and s.has_reps,
        value_fn=lambda s: s.last_volume_kg,
    ),
    HevyExerciseSensorEntityDescription(
        key="last_performed",
        translation_key="exercise_last_performed",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda s: s.last_performed,
        attrs_fn=_exercise_attrs,
    ),
    HevyExerciseSensorEntityDescription(
        key="max_reps",
        translation_key="exercise_max_reps",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        exists_fn=lambda s: s.has_reps,
        value_fn=lambda s: s.max_reps,
    ),
    # Totals
    HevyExerciseSensorEntityDescription(
        key="workout_count",
        translation_key="exercise_workout_count",
        state_class=SensorStateClass.TOTAL,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.workout_count,
    ),
    HevyExerciseSensorEntityDescription(
        key="total_sets",
        translation_key="exercise_total_sets",
        state_class=SensorStateClass.TOTAL,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.total_sets,
    ),
    HevyExerciseSensorEntityDescription(
        key="total_reps",
        translation_key="exercise_total_reps",
        state_class=SensorStateClass.TOTAL,
        entity_registry_enabled_default=False,
        exists_fn=lambda s: s.has_reps,
        value_fn=lambda s: s.total_reps,
    ),
    HevyExerciseSensorEntityDescription(
        key="total_volume",
        translation_key="exercise_total_volume",
        **_weight(state_class=SensorStateClass.TOTAL, suggested_display_precision=0),
        entity_registry_enabled_default=False,
        exists_fn=lambda s: s.has_weight and s.has_reps,
        value_fn=lambda s: s.total_volume_kg,
    ),
    # Last workout
    HevyExerciseSensorEntityDescription(
        key="last_sets",
        translation_key="exercise_last_sets",
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.last_sets,
    ),
    HevyExerciseSensorEntityDescription(
        key="last_reps",
        translation_key="exercise_last_reps",
        entity_registry_enabled_default=False,
        exists_fn=lambda s: s.has_reps,
        value_fn=lambda s: s.last_reps,
    ),
    HevyExerciseSensorEntityDescription(
        key="last_top_weight",
        translation_key="exercise_last_top_weight",
        **_weight(state_class=SensorStateClass.MEASUREMENT),
        entity_registry_enabled_default=False,
        exists_fn=lambda s: s.has_weight,
        value_fn=lambda s: s.last_top_weight_kg,
    ),
    # Cardio
    HevyExerciseSensorEntityDescription(
        key="max_distance",
        translation_key="exercise_max_distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.METERS,
        suggested_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        exists_fn=lambda s: s.has_distance,
        value_fn=lambda s: s.max_distance_m,
    ),
    HevyExerciseSensorEntityDescription(
        key="total_distance",
        translation_key="exercise_total_distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.METERS,
        suggested_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=1,
        state_class=SensorStateClass.TOTAL,
        entity_registry_enabled_default=False,
        exists_fn=lambda s: s.has_distance,
        value_fn=lambda s: s.total_distance_m,
    ),
    HevyExerciseSensorEntityDescription(
        key="max_duration",
        translation_key="exercise_max_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        exists_fn=lambda s: s.has_duration,
        value_fn=lambda s: s.max_duration_s,
    ),
    HevyExerciseSensorEntityDescription(
        key="total_duration",
        translation_key="exercise_total_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        state_class=SensorStateClass.TOTAL,
        entity_registry_enabled_default=False,
        exists_fn=lambda s: s.has_duration,
        value_fn=lambda s: s.total_duration_s,
    ),
)


@dataclass(frozen=True, kw_only=True)
class HevyRoutineSensorEntityDescription(SensorEntityDescription):
    """Describes a per-routine sensor."""

    value_fn: Callable[[RoutineStats], StateType | datetime]
    attrs_fn: Callable[[RoutineStats], dict[str, Any]] | None = None


def _routine_attrs(stats: RoutineStats) -> dict[str, Any]:
    return {
        "routine_id": stats.routine_id,
        "folder_id": stats.folder_id,
        "folder_name": stats.folder_name,
        "last_workout_id": stats.last_workout_id,
        "exercises": stats.exercises,
    }


ROUTINE_SENSORS: tuple[HevyRoutineSensorEntityDescription, ...] = (
    HevyRoutineSensorEntityDescription(
        key="last_volume",
        translation_key="routine_last_volume",
        **_weight(
            state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=0
        ),
        value_fn=lambda s: s.last_volume_kg,
        attrs_fn=_routine_attrs,
    ),
    HevyRoutineSensorEntityDescription(
        key="previous_volume",
        translation_key="routine_previous_volume",
        **_weight(
            state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=0
        ),
        value_fn=lambda s: s.previous_volume_kg,
    ),
    HevyRoutineSensorEntityDescription(
        key="volume_change",
        translation_key="routine_volume_change",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s: s.volume_change_pct,
    ),
    HevyRoutineSensorEntityDescription(
        key="last_performed",
        translation_key="routine_last_performed",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda s: s.last_performed,
    ),
    HevyRoutineSensorEntityDescription(
        key="workout_count",
        translation_key="routine_workout_count",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda s: s.workout_count,
    ),
    HevyRoutineSensorEntityDescription(
        key="last_duration",
        translation_key="routine_last_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.last_duration_min,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HevyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hevy sensors."""
    coordinator = entry.runtime_data
    async_add_entities(HevySensor(coordinator, description) for description in SENSORS)

    known: set[tuple[str, str, str]] = set()

    @callback
    def _add_new_entities() -> None:
        """Add sensors for exercises/routines (and data types) not seen before."""
        data = coordinator.data
        new: list[SensorEntity] = []
        for template_id, stats in data.exercises.items():
            for description in EXERCISE_SENSORS:
                key = ("exercise", template_id, description.key)
                if key in known or not description.exists_fn(stats):
                    continue
                known.add(key)
                new.append(HevyExerciseSensor(coordinator, template_id, description))
        for routine_id in data.routine_stats:
            for routine_description in ROUTINE_SENSORS:
                key = ("routine", routine_id, routine_description.key)
                if key in known:
                    continue
                known.add(key)
                new.append(
                    HevyRoutineSensor(coordinator, routine_id, routine_description)
                )
        if new:
            async_add_entities(new)

    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class HevySensor(HevyEntity, SensorEntity):
    """A sensor on the account device."""

    entity_description: HevySensorEntityDescription

    def __init__(
        self,
        coordinator: HevyCoordinator,
        description: HevySensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | date | datetime:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)


class HevyExerciseSensor(HevyExerciseEntity, SensorEntity):
    """A sensor on an exercise device."""

    entity_description: HevyExerciseSensorEntityDescription

    def __init__(
        self,
        coordinator: HevyCoordinator,
        template_id: str,
        description: HevyExerciseSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, template_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        """Return the state."""
        stats = self.stats
        return self.entity_description.value_fn(stats) if stats else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        stats = self.stats
        if self.entity_description.attrs_fn is None or stats is None:
            return None
        return self.entity_description.attrs_fn(stats)


class HevyRoutineSensor(HevyRoutineEntity, SensorEntity):
    """A sensor on a routine device."""

    entity_description: HevyRoutineSensorEntityDescription

    def __init__(
        self,
        coordinator: HevyCoordinator,
        routine_id: str,
        description: HevyRoutineSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, routine_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        """Return the state."""
        stats = self.stats
        return self.entity_description.value_fn(stats) if stats else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        stats = self.stats
        if self.entity_description.attrs_fn is None or stats is None:
            return None
        return self.entity_description.attrs_fn(stats)
