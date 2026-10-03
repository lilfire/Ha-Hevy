"""Constants for the Hevy integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "hevy"

API_BASE_URL: Final = "https://api.hevyapp.com"

CONF_SCAN_INTERVAL: Final = "scan_interval"
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=15)
MIN_SCAN_INTERVAL_MINUTES: Final = 5
MAX_SCAN_INTERVAL_MINUTES: Final = 1440

# How far back the coordinator keeps workouts in memory for statistics sensors.
RECENT_WORKOUT_DAYS: Final = 30
# Safety cap on the number of pages fetched when loading recent workouts.
MAX_WORKOUT_PAGES: Final = 20
# Safety cap on the number of pages fetched for routines / routine folders.
MAX_LIST_PAGES: Final = 50

# Hevy page-size limits (from the public API spec).
MAX_PAGE_SIZE: Final = 10
MAX_TEMPLATE_PAGE_SIZE: Final = 100

EVENT_NEW_WORKOUT: Final = "hevy_new_workout"

SET_TYPES: Final = ["warmup", "normal", "failure", "dropset"]
RPE_VALUES: Final = [6, 7, 7.5, 8, 8.5, 9, 9.5, 10]
MUSCLE_GROUPS: Final = [
    "abdominals",
    "shoulders",
    "biceps",
    "triceps",
    "forearms",
    "quadriceps",
    "hamstrings",
    "calves",
    "glutes",
    "abductors",
    "adductors",
    "lats",
    "upper_back",
    "traps",
    "lower_back",
    "chest",
    "cardio",
    "neck",
    "full_body",
    "other",
]
EXERCISE_TYPES: Final = [
    "weight_reps",
    "reps_only",
    "bodyweight_reps",
    "bodyweight_assisted_reps",
    "duration",
    "weight_duration",
    "distance_duration",
    "short_distance_weight",
]
EQUIPMENT_CATEGORIES: Final = [
    "none",
    "barbell",
    "dumbbell",
    "kettlebell",
    "machine",
    "plate",
    "resistance_band",
    "suspension",
    "other",
]

BODY_MEASUREMENT_FIELDS: Final = [
    "weight_kg",
    "lean_mass_kg",
    "fat_percent",
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
]
