"""Pure statistics over Hevy workouts (no Home Assistant state)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
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
    last_workout_sets: list[JSON] = field(default_factory=list)
    distance_this_week_m: float = 0.0

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


def set_summary(workout_set: JSON) -> JSON:
    """Compact representation of a logged set."""
    return {
        key: workout_set.get(source)
        for key, source in (
            ("type", "type"),
            ("weight_kg", "weight_kg"),
            ("reps", "reps"),
            ("rpe", "rpe"),
            ("distance_m", "distance_meters"),
            ("duration_s", "duration_seconds"),
        )
        if workout_set.get(source) is not None
    }


def start_of_week(now: datetime | None = None) -> datetime:
    """Monday 00:00 local time of the current week, as UTC."""
    today = dt_util.start_of_local_day(dt_util.as_local(now) if now else None)
    return dt_util.as_utc(today - timedelta(days=today.weekday()))


def exercise_stats(
    workouts: list[JSON],
    templates: dict[str, JSON] | None = None,
    now: datetime | None = None,
) -> dict[str, ExerciseStats]:
    """Aggregate statistics per exercise template over all workouts."""
    templates = templates or {}
    week_start = start_of_week(now)
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
            item.last_workout_sets = [
                set_summary(s) for s in exercise.get("sets") or []
            ]
            if started is not None and started >= week_start:
                item.distance_this_week_m += sum(
                    _num(s.get("distance_meters")) or 0.0 for s in sets
                )
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


# --------------------------------------------------------------- account-wide


def training_days(workouts: list[JSON]) -> list[date]:
    """Sorted unique local dates with at least one workout."""
    days = {
        dt_util.as_local(started).date()
        for w in workouts
        if (started := parse_time(w.get("start_time"))) is not None
    }
    return sorted(days)


@dataclass
class Streak:
    """Workout streak, allowing one rest day between training days."""

    current: int = 0
    longest: int = 0
    current_start: date | None = None
    last_training_day: date | None = None


def streak(days: list[date], today: date, max_gap: int = 2) -> Streak:
    """Count training days in chains where days are at most ``max_gap`` apart.

    ``max_gap = 2`` allows a single rest day. The current streak is 0 when the
    last training day is more than ``max_gap`` days ago.
    """
    result = Streak()
    if not days:
        return result
    run = 1
    run_start = days[0]
    result.longest = 1
    for prev, day in zip(days, days[1:], strict=False):
        if (day - prev).days <= max_gap:
            run += 1
        else:
            run = 1
            run_start = day
        result.longest = max(result.longest, run)
    result.last_training_day = days[-1]
    if (today - days[-1]).days <= max_gap:
        result.current = run
        result.current_start = run_start
    return result


def _muscles(template: JSON) -> tuple[str | None, list[str]]:
    return template.get("primary_muscle_group"), list(
        template.get("secondary_muscle_groups") or []
    )


@dataclass
class MuscleSummary:
    """Muscle groups trained, recency and due groups."""

    last_workout_primary: list[str] = field(default_factory=list)
    last_workout_secondary: list[str] = field(default_factory=list)
    last_workout_date: datetime | None = None
    days_since_last: dict[str, int] = field(default_factory=dict)
    muscles_due: list[str] = field(default_factory=list)


def muscle_summary(
    workouts: list[JSON], templates: dict[str, JSON], today: date, due_days: int
) -> MuscleSummary:
    """Summarise muscle groups from workouts (newest first or any order)."""
    result = MuscleSummary()
    ordered = sorted(workouts, key=lambda w: w.get("start_time") or "", reverse=True)
    last_trained: dict[str, date] = {}
    for index, workout in enumerate(ordered):
        started = parse_time(workout.get("start_time"))
        if started is None:
            continue
        day = dt_util.as_local(started).date()
        primary: list[str] = []
        secondary: list[str] = []
        for exercise in workout.get("exercises") or []:
            main, others = _muscles(
                templates.get(exercise.get("exercise_template_id") or "") or {}
            )
            if main and main not in primary:
                primary.append(main)
            secondary.extend(m for m in others if m not in secondary)
            if main:
                last_trained.setdefault(main, day)
        if index == 0:
            result.last_workout_primary = primary
            result.last_workout_secondary = [m for m in secondary if m not in primary]
            result.last_workout_date = started
    result.days_since_last = {
        muscle: (today - day).days
        for muscle, day in sorted(
            last_trained.items(), key=lambda kv: kv[1], reverse=True
        )
    }
    result.muscles_due = [
        muscle for muscle, days in result.days_since_last.items() if days >= due_days
    ]
    return result


@dataclass
class MuscleVolume:
    """Volume per primary muscle group within a period."""

    total_kg: float = 0.0
    muscle_groups: dict[str, float] = field(default_factory=dict)
    exercise_breakdown: dict[str, list[JSON]] = field(default_factory=dict)
    total_sets: int = 0
    total_workouts: int = 0


def muscle_volume(
    workouts: list[JSON], templates: dict[str, JSON], since: datetime
) -> MuscleVolume:
    """Working-set volume per primary muscle group since ``since``."""
    result = MuscleVolume()
    per_exercise: dict[tuple[str, str], JSON] = {}
    for workout in workouts:
        started = parse_time(workout.get("start_time"))
        if started is None or started < since:
            continue
        result.total_workouts += 1
        for exercise in workout.get("exercises") or []:
            template = templates.get(exercise.get("exercise_template_id") or "") or {}
            muscle = template.get("primary_muscle_group") or "other"
            sets = working_sets(exercise)
            volume = exercise_volume_kg(exercise)
            result.total_sets += len(sets)
            result.total_kg += volume
            result.muscle_groups[muscle] = (
                result.muscle_groups.get(muscle, 0.0) + volume
            )
            title = template.get("title") or exercise.get("title") or "?"
            entry = per_exercise.setdefault(
                (muscle, title), {"exercise": title, "volume": 0.0, "sets": 0}
            )
            entry["volume"] += volume
            entry["sets"] += len(sets)
    result.total_kg = round(result.total_kg, 2)
    result.muscle_groups = {
        k: round(v, 2)
        for k, v in sorted(result.muscle_groups.items(), key=lambda kv: -kv[1])
    }
    for (muscle, _title), entry in per_exercise.items():
        entry["volume"] = round(entry["volume"], 2)
        result.exercise_breakdown.setdefault(muscle, []).append(entry)
    for entries in result.exercise_breakdown.values():
        entries.sort(key=lambda e: -e["volume"])
    return result


@dataclass
class NextRoutine:
    """Suggested next routine in the rotation."""

    routine_id: str
    routine_title: str
    folder_id: int | None
    last_routine_id: str | None
    last_routine_title: str | None
    rotation_position: int
    rotation_total: int
    exercises_preview: list[str]


def next_routine(workouts: list[JSON], routines: list[JSON]) -> NextRoutine | None:
    """Pick the next routine of the rotation.

    The rotation is the folder of the most recently performed routine. The
    next routine is the one in that folder done least recently (never-done
    routines first, then by title). Hevy's API exposes no routine order, so
    this reproduces an A/B/C rotation from history.
    """
    by_id = {r.get("id"): r for r in routines if r.get("id")}
    last_done: dict[str, str] = {}
    last_routine: JSON | None = None
    for workout in sorted(workouts, key=lambda w: w.get("start_time") or ""):
        routine_id = workout.get("routine_id")
        if routine_id in by_id:
            last_done[routine_id] = workout.get("start_time") or ""
            last_routine = by_id[routine_id]
    if last_routine is None:
        return None
    folder_id = last_routine.get("folder_id")
    candidates = sorted(
        (r for r in routines if r.get("folder_id") == folder_id and r.get("id")),
        key=lambda r: r.get("title") or "",
    )
    if len(candidates) < 2:
        candidates = [last_routine]
    ordered = sorted(
        candidates, key=lambda r: (last_done.get(r["id"], ""), r.get("title") or "")
    )
    choice = ordered[0]
    if len(candidates) > 1 and choice["id"] == last_routine.get("id"):
        choice = ordered[1]
    return NextRoutine(
        routine_id=choice["id"],
        routine_title=choice.get("title") or choice["id"],
        folder_id=folder_id,
        last_routine_id=last_routine.get("id"),
        last_routine_title=last_routine.get("title"),
        rotation_position=[r["id"] for r in candidates].index(choice["id"]) + 1,
        rotation_total=len(candidates),
        exercises_preview=[
            e.get("title") for e in choice.get("exercises") or [] if e.get("title")
        ],
    )


def workout_summary(workout: JSON, templates: dict[str, JSON]) -> JSON:
    """Enriched, compact description of one workout."""
    exercises = []
    primary: list[str] = []
    for exercise in workout.get("exercises") or []:
        template = templates.get(exercise.get("exercise_template_id") or "") or {}
        if (muscle := template.get("primary_muscle_group")) and muscle not in primary:
            primary.append(muscle)
        best = None
        for workout_set in working_sets(exercise):
            weight = _num(workout_set.get("weight_kg"))
            reps = _num(workout_set.get("reps"))
            if (
                weight
                and reps
                and (best is None or estimated_1rm(weight, reps) > best[2])
            ):
                best = (weight, int(reps), estimated_1rm(weight, reps))
        exercises.append(
            {
                "title": exercise.get("title"),
                "exercise_template_id": exercise.get("exercise_template_id"),
                "notes": exercise.get("notes") or None,
                "sets": [set_summary(s) for s in exercise.get("sets") or []],
                "best_set": f"{best[0]:g} kg × {best[1]}" if best else None,
                "volume_kg": round(exercise_volume_kg(exercise), 2),
            }
        )
    return {
        "id": workout.get("id"),
        "title": workout.get("title"),
        "routine_id": workout.get("routine_id"),
        "start_time": workout.get("start_time"),
        "end_time": workout.get("end_time"),
        "duration_minutes": workout_duration_minutes(workout),
        "volume_kg": workout_volume_kg(workout),
        "set_count": workout_set_count(workout),
        "muscle_groups": primary,
        "exercises": exercises,
    }
