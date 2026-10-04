"""Tests for the pure statistics helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from custom_components.hevy.stats import (
    estimated_1rm,
    exercise_stats,
    muscle_summary,
    muscle_volume,
    next_routine,
    routine_stats,
    streak,
    workout_summary,
    workout_volume_kg,
)


def _workout(wid, start, exercises, routine_id=None):
    return {
        "id": wid,
        "title": f"W {wid}",
        "routine_id": routine_id,
        "start_time": start,
        "end_time": start.replace("T10", "T11"),
        "exercises": exercises,
    }


def _ex(tid, sets, title="Bench"):
    return {"exercise_template_id": tid, "title": title, "sets": sets}


BENCH_OLD = _workout(
    "a",
    "2026-01-01T10:00:00Z",
    [
        _ex(
            "B",
            [
                {"type": "warmup", "weight_kg": 200, "reps": 10},
                {"type": "normal", "weight_kg": 100, "reps": 5},
                {"type": "failure", "weight_kg": 90, "reps": 10},
            ],
        )
    ],
    routine_id="r1",
)
BENCH_NEW = _workout(
    "b",
    "2026-02-01T10:00:00Z",
    [
        _ex("B", [{"type": "normal", "weight_kg": 105, "reps": 1}]),
        _ex(
            "RUN",
            [{"type": "normal", "distance_meters": 5000, "duration_seconds": 1500}],
            title="Running",
        ),
    ],
    routine_id="r1",
)


def test_epley() -> None:
    """Epley formula, with 1 rep equal to the weight."""
    assert estimated_1rm(100, 1) == 100
    assert estimated_1rm(100, 5) == 100 * (1 + 5 / 30)


def test_warmups_excluded_from_volume() -> None:
    """Warm-up sets do not count towards volume."""
    assert workout_volume_kg(BENCH_OLD) == 100 * 5 + 90 * 10


def test_exercise_stats() -> None:
    """All-time and last-workout statistics."""
    stats = exercise_stats(
        [BENCH_NEW, BENCH_OLD], {"B": {"title": "Bench Press", "type": "weight_reps"}}
    )
    bench = stats["B"]
    assert bench.title == "Bench Press"
    assert bench.max_weight_kg == 105  # warm-up 200 kg ignored
    assert bench.max_weight_date.isoformat().startswith("2026-02-01")
    # 90x10 -> 120 beats 100x5 -> 116.7 and 105x1 -> 105.
    assert bench.best_set.weight_kg == 90
    assert bench.best_set.estimated_1rm == 120.0
    assert bench.workout_count == 2
    assert bench.total_sets == 3
    assert bench.total_reps == 16
    assert bench.total_volume_kg == 1400 + 105
    assert bench.max_reps == 10
    assert bench.last_workout_id == "b"
    assert bench.last_volume_kg == 105
    assert bench.last_sets == 1
    assert bench.last_top_weight_kg == 105
    assert bench.has_weight and bench.has_reps
    assert not bench.has_distance

    run = stats["RUN"]
    assert run.title == "Running"
    assert run.has_distance and run.has_duration
    assert not run.has_weight
    assert run.max_distance_m == 5000
    assert run.total_duration_s == 1500
    assert run.best_set is None


def test_routine_stats() -> None:
    """Last/previous volume and folder name per routine."""
    stats = routine_stats(
        [BENCH_OLD, BENCH_NEW],
        [
            {
                "id": "r1",
                "title": "Push",
                "folder_id": 7,
                "exercises": [{"title": "Bench"}],
            },
            {"id": "r2", "title": "Never done", "folder_id": None},
        ],
        [{"id": 7, "title": "Block 1"}],
    )
    push = stats["r1"]
    assert push.folder_name == "Block 1"
    assert push.workout_count == 2
    assert push.last_workout_id == "b"
    assert push.last_volume_kg == 105
    assert push.previous_volume_kg == 1400
    assert push.volume_change_pct == round((105 - 1400) / 1400 * 100, 1)
    assert push.last_duration_min == 60.0
    assert push.exercises == ["Bench"]
    never = stats["r2"]
    assert never.workout_count == 0
    assert never.last_volume_kg is None
    assert never.volume_change_pct is None


def test_streak_allows_one_rest_day() -> None:
    """Gaps of one rest day keep the streak, two break it."""
    d = date(2026, 3, 1)
    days = [d, d + timedelta(days=2), d + timedelta(days=3), d + timedelta(days=6)]
    # Gap 3->6 has two rest days: chain restarts at day 6.
    result = streak(days, d + timedelta(days=7))
    assert result.current == 1
    assert result.longest == 3
    assert result.current_start == d + timedelta(days=6)
    # Today two days after the last session: still alive.
    assert streak(days[:3], d + timedelta(days=5)).current == 3
    # Three days after: broken.
    assert streak(days[:3], d + timedelta(days=6)).current == 0
    assert streak([], d).current == 0


TEMPLATES = {
    "B": {
        "title": "Bench",
        "primary_muscle_group": "chest",
        "secondary_muscle_groups": ["triceps"],
    },
    "RUN": {"title": "Running", "primary_muscle_group": "cardio"},
    "SQ": {"title": "Squat", "primary_muscle_group": "quadriceps"},
}


def test_muscle_summary_and_volume() -> None:
    """Muscle recency, due groups and weekly volume per group."""
    squat = _workout(
        "c",
        "2026-01-20T10:00:00Z",
        [_ex("SQ", [{"weight_kg": 100, "reps": 5}], "Squat")],
    )
    workouts = [BENCH_OLD, BENCH_NEW, squat]
    summary = muscle_summary(workouts, TEMPLATES, date(2026, 2, 3), due_days=4)
    assert summary.last_workout_primary == ["chest", "cardio"]
    assert summary.last_workout_secondary == ["triceps"]
    assert summary.days_since_last == {"chest": 2, "cardio": 2, "quadriceps": 14}
    assert summary.muscles_due == ["quadriceps"]

    since = datetime(2026, 1, 15, tzinfo=UTC)
    volume = muscle_volume(workouts, TEMPLATES, since)
    assert volume.total_workouts == 2
    assert volume.muscle_groups == {"quadriceps": 500.0, "chest": 105.0, "cardio": 0.0}
    assert volume.exercise_breakdown["chest"] == [
        {"exercise": "Bench", "volume": 105.0, "sets": 1}
    ]
    assert volume.total_kg == 605.0


def test_next_routine_rotation() -> None:
    """Least recently done routine in the same folder is next."""
    routines = [
        {
            "id": "A",
            "title": "Day A",
            "folder_id": 1,
            "exercises": [{"title": "Bench"}],
        },
        {"id": "B", "title": "Day B", "folder_id": 1},
        {"id": "C", "title": "Day C", "folder_id": 1},
        {"id": "X", "title": "Other", "folder_id": 2},
    ]
    history = [
        _workout("1", "2026-01-01T10:00:00Z", [], routine_id="A"),
        _workout("2", "2026-01-03T10:00:00Z", [], routine_id="B"),
    ]
    nxt = next_routine(history, routines)
    assert nxt.routine_id == "C"  # never done comes first
    assert nxt.rotation_position == 3 and nxt.rotation_total == 3
    history.append(_workout("3", "2026-01-05T10:00:00Z", [], routine_id="C"))
    assert next_routine(history, routines).routine_id == "A"
    assert next_routine(history, routines).exercises_preview == ["Bench"]
    assert next_routine([], routines) is None


def test_workout_summary_and_last_sets() -> None:
    """Enriched summary and last-workout set details."""
    summary = workout_summary(BENCH_OLD, TEMPLATES)
    assert summary["muscle_groups"] == ["chest"]
    assert summary["exercises"][0]["best_set"] == "90 kg × 10"
    assert summary["exercises"][0]["sets"][0] == {
        "type": "warmup",
        "weight_kg": 200,
        "reps": 10,
    }
    stats = exercise_stats(
        [BENCH_OLD, BENCH_NEW], TEMPLATES, now=datetime(2026, 2, 4, 12, tzinfo=UTC)
    )
    assert stats["B"].last_workout_sets == [
        {"type": "normal", "weight_kg": 105, "reps": 1}
    ]
    # 2026-02-01 (Sunday) is in the week before Wednesday 2026-02-04.
    assert stats["RUN"].distance_this_week_m == 0
    stats = exercise_stats(
        [BENCH_NEW], TEMPLATES, now=datetime(2026, 2, 1, 12, tzinfo=UTC)
    )
    assert stats["RUN"].distance_this_week_m == 5000
