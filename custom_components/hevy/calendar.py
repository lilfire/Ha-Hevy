"""Calendar of completed Hevy workouts."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import JSON
from .coordinator import HevyConfigEntry, HevyCoordinator
from .entity import HevyEntity
from .stats import parse_time, workout_summary

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HevyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Hevy calendar."""
    async_add_entities([HevyWorkoutCalendar(entry.runtime_data)])


def _description(summary: JSON) -> str:
    lines: list[str] = []
    meta = []
    if summary.get("duration_minutes") is not None:
        meta.append(f"{summary['duration_minutes']:g} min")
    if summary.get("volume_kg"):
        meta.append(f"{summary['volume_kg']:g} kg")
    if summary.get("muscle_groups"):
        meta.append(", ".join(summary["muscle_groups"]))
    if meta:
        lines.append(" · ".join(meta))
    for exercise in summary.get("exercises") or []:
        line = f"• {exercise.get('title')}: {len(exercise.get('sets') or [])} sets"
        if exercise.get("best_set"):
            line += f" (best {exercise['best_set']})"
        lines.append(line)
    return "\n".join(lines)


class HevyWorkoutCalendar(HevyEntity, CalendarEntity):
    """Completed workouts as calendar events."""

    _attr_translation_key = "workouts"

    def __init__(self, coordinator: HevyCoordinator) -> None:
        """Initialize the calendar."""
        super().__init__(coordinator, "workout_calendar")

    def _event(self, workout: JSON) -> CalendarEvent | None:
        start = parse_time(workout.get("start_time"))
        end = parse_time(workout.get("end_time")) or start
        if start is None or end is None:
            return None
        if end <= start:
            end = start + timedelta(minutes=1)
        summary = workout_summary(workout, self.coordinator.data.templates)
        return CalendarEvent(
            start=start,
            end=end,
            summary=workout.get("title") or "Workout",
            description=_description(summary),
            uid=workout.get("id"),
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return a workout in progress (completed workouts only exist afterwards)."""
        now = dt_util.utcnow()
        latest = self.coordinator.data.latest_workout
        if latest is None:
            return None
        event = self._event(latest)
        if event is None or not event.start <= now < event.end:
            return None
        return event

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return workouts overlapping the requested range."""
        events = []
        for workout in reversed(self.coordinator.data.workouts):
            event = self._event(workout)
            if event and event.end > start_date and event.start < end_date:
                events.append(event)
        return events
