"""Tests for the pure statistics helpers."""

from __future__ import annotations

from custom_components.hevy.stats import (
    estimated_1rm,
    exercise_stats,
    routine_stats,
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
