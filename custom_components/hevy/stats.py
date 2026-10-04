"""Pure statistics over Hevy workouts (no Home Assistant state)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

type JSON = dict[str, Any]

WARMUP = "warmup"


def parse_time(value: Any) -> datetime | None:
    """Parse a Hevy ISO 8601 timestamp to an aware UTC datetime."""
    if not isinstance(value, str):
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return dt_util.as_utc(parsed)


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def working_sets(exercise: JSON) -> list[JSON]:
    """Sets of an exercise, excluding warm-up sets."""
    return [s for s in exercise.get("sets") or [] if s.get("type") != WARMUP]


def exercise_volume_kg(exercise: JSON) -> float:
    """Weight x reps over the working sets of one exercise."""
    total = 0.0
    for workout_set in working_sets(exercise):
        weight = _num(workout_set.get("weight_kg"))
        reps = _num(workout_set.get("reps"))
        if weight is not None and reps is not None:
            total += weight * reps
    return total


def workout_volume_kg(workout: JSON) -> float:
    """Total volume (weight x reps, warm-ups excluded) of a workout in kg."""
    return round(
        sum(exercise_volume_kg(ex) for ex in workout.get("exercises") or []), 2
    )


def workout_set_count(workout: JSON) -> int:
    """Number of sets in a workout."""
    return sum(len(ex.get("sets") or []) for ex in workout.get("exercises") or [])


def workout_duration_minutes(workout: JSON) -> float | None:
    """Duration of a workout in minutes."""
    start = parse_time(workout.get("start_time"))
    end = parse_time(workout.get("end_time"))
    if start is None or end is None or end < start:
        return None
    return round((end - start).total_seconds() / 60, 1)


def estimated_1rm(weight: float, reps: float) -> float:
    """Epley estimate of the one-rep max."""
    if reps <= 1:
        return weight
    return weight * (1 + reps / 30)


@dataclass
class BestSet:
    """The set that gave the best estimated 1RM."""

    weight_kg: float
    reps: int
    estimated_1rm: float
    workout_id: str | None
    date: datetime | None


@dataclass
class ExerciseStats:
    """All-time statistics for one exercise template."""

    exercise_template_id: str
    title: str
    template: JSON = field(default_factory=dict)
    workout_count: int = 0
    total_sets: int = 0
    total_reps: int = 0
    total_volume_kg: float = 0.0
    max_weight_kg: float | None = None
    max_weight_date: datetime | None = None
    max_reps: int | None = None
    best_set: BestSet | None = None
    max_distance_m: float | None = None
    total_distance_m: float = 0.0
    max_duration_s: float | None = None
    total_duration_s: float = 0.0
    last_performed: datetime | None = None
    last_workout_id: str | None = None
    last_workout_title: str | None = None
    last_volume_kg: float | None = None
    last_sets: int | None = None
    last_reps: int | None = None
    last_top_weight_kg: float | None = None

    @property
    def has_weight(self) -> bool:
        """Whether any working set logged a weight."""
        return self.max_weight_kg is not None and self.max_weight_kg > 0

    @property
    def has_reps(self) -> bool:
        """Whether any working set logged reps."""
        return self.max_reps is not None and self.max_reps > 0

    @property
    def has_distance(self) -> bool:
        """Whether any working set logged a distance."""
        return self.max_distance_m is not None and self.max_distance_m > 0

    @property
    def has_duration(self) -> bool:
        """Whether any working set logged a duration."""
        return self.max_duration_s is not None and self.max_duration_s > 0


def _max(current: float | None, value: float | None) -> float | None:
    if value is None:
        return current
    return value if current is None else max(current, value)


def exercise_stats(
    workouts: list[JSON], templates: dict[str, JSON] | None = None
) -> dict[str, ExerciseStats]:
    """Aggregate statistics per exercise template over all workouts."""
    templates = templates or {}
    stats: dict[str, ExerciseStats] = {}
    ordered = sorted(workouts, key=lambda w: w.get("start_time") or "")
    for workout in ordered:
        started = parse_time(workout.get("start_time"))
        for exercise in workout.get("exercises") or []:
            template_id = exercise.get("exercise_template_id")
            if not template_id:
                continue
            template = templates.get(template_id) or {}
            item = stats.get(template_id)
            if item is None:
                item = stats[template_id] = ExerciseStats(
                    exercise_template_id=template_id,
                    title=template.get("title") or exercise.get("title") or template_id,
                    template=template,
                )
            sets = working_sets(exercise)
            item.workout_count += 1
            item.total_sets += len(sets)

            reps_sum = 0
            top_weight: float | None = None
            for workout_set in sets:
                weight = _num(workout_set.get("weight_kg"))
                reps = _num(workout_set.get("reps"))
                distance = _num(workout_set.get("distance_meters"))
                duration = _num(workout_set.get("duration_seconds"))
                if reps is not None:
                    reps_sum += int(reps)
                    item.max_reps = int(_max(item.max_reps, reps) or 0)
                if weight is not None:
                    top_weight = _max(top_weight, weight)
                    if item.max_weight_kg is None or weight > item.max_weight_kg:
                        item.max_weight_kg = weight
                        item.max_weight_date = started
                if weight and reps and weight > 0 and reps > 0:
                    e1rm = estimated_1rm(weight, reps)
                    if item.best_set is None or e1rm > item.best_set.estimated_1rm:
                        item.best_set = BestSet(
                            weight_kg=weight,
                            reps=int(reps),
                            estimated_1rm=round(e1rm, 1),
                            workout_id=workout.get("id"),
                            date=started,
                        )
                if distance is not None:
                    item.total_distance_m += distance
                    item.max_distance_m = _max(item.max_distance_m, distance)
                if duration is not None:
                    item.total_duration_s += duration
                    item.max_duration_s = _max(item.max_duration_s, duration)

            volume = exercise_volume_kg(exercise)
            item.total_reps += reps_sum
            item.total_volume_kg = round(item.total_volume_kg + volume, 2)
            # Workouts are iterated oldest first, so the last one wins.
            item.last_performed = started
            item.last_workout_id = workout.get("id")
            item.last_workout_title = workout.get("title")
            item.last_volume_kg = round(volume, 2)
            item.last_sets = len(sets)
            item.last_reps = reps_sum
            item.last_top_weight_kg = top_weight
    return stats


@dataclass
class RoutineStats:
    """Statistics for one routine, based on the workouts started from it."""

    routine_id: str
    title: str
    folder_id: int | None = None
    folder_name: str | None = None
    exercises: list[str] = field(default_factory=list)
    workout_count: int = 0
    last_performed: datetime | None = None
    last_workout_id: str | None = None
    last_volume_kg: float | None = None
    previous_volume_kg: float | None = None
    last_duration_min: float | None = None

    @property
    def volume_change_pct(self) -> float | None:
        """Change in volume from the previous to the last workout."""
        if not self.previous_volume_kg or self.last_volume_kg is None:
            return None
        return round(
            (self.last_volume_kg - self.previous_volume_kg)
            / self.previous_volume_kg
            * 100,
            1,
        )


def routine_stats(
    workouts: list[JSON], routines: list[JSON], folders: list[JSON]
) -> dict[str, RoutineStats]:
    """Statistics for every routine that still exists in Hevy."""
    folder_names = {f.get("id"): f.get("title") for f in folders}
    by_routine: dict[str, list[JSON]] = {}
    for workout in workouts:
        if routine_id := workout.get("routine_id"):
            by_routine.setdefault(routine_id, []).append(workout)

    result: dict[str, RoutineStats] = {}
    for routine in routines:
        routine_id = routine.get("id")
        if not routine_id:
            continue
        item = RoutineStats(
            routine_id=routine_id,
            title=routine.get("title") or routine_id,
            folder_id=routine.get("folder_id"),
            folder_name=folder_names.get(routine.get("folder_id")),
            exercises=[
                e.get("title") for e in routine.get("exercises") or [] if e.get("title")
            ],
        )
        history = sorted(
            by_routine.get(routine_id, []), key=lambda w: w.get("start_time") or ""
        )
        item.workout_count = len(history)
        if history:
            last = history[-1]
            item.last_performed = parse_time(last.get("start_time"))
            item.last_workout_id = last.get("id")
            item.last_volume_kg = workout_volume_kg(last)
            item.last_duration_min = workout_duration_minutes(last)
        if len(history) > 1:
            item.previous_volume_kg = workout_volume_kg(history[-2])
        result[routine_id] = item
    return result
