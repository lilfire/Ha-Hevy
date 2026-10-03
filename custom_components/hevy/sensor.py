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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .api import JSON
from .coordinator import (
    HevyConfigEntry,
    HevyCoordinator,
    HevyData,
    parse_time,
    workout_duration_minutes,
    workout_set_count,
    workout_volume_kg,
)
from .entity import HevyEntity

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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HevyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hevy sensors."""
    coordinator = entry.runtime_data
    async_add_entities(HevySensor(coordinator, description) for description in SENSORS)


class HevySensor(HevyEntity, SensorEntity):
    """A Hevy sensor."""

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
