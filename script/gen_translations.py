"""Generate services.yaml, strings.json, icons.json and translations.

Run from the repository root: ``python script/gen_translations.py``.
Single source of truth for service fields and their English/Norwegian texts.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parent.parent / "custom_components" / "hevy"

sys.path.insert(0, str(ROOT))
from const import (  # noqa: E402
    EQUIPMENT_CATEGORIES,
    EXERCISE_TYPES,
    MUSCLE_GROUPS,
    SET_TYPES,
)

sys.path.pop(0)

# --------------------------------------------------------------------- fields
# key: (selector, required, example, (en name, en desc), (nb name, nb desc))


def num(min_, max_=None, step=1, unit=None):
    cfg = {"min": min_, "step": step, "mode": "box"}
    if max_ is not None:
        cfg["max"] = max_
    if unit:
        cfg["unit_of_measurement"] = unit
    return {"number": cfg}


TEXT = {"text": None}
DATETIME = {"datetime": None}
DATE = {"date": None}
OBJECT = {"object": None}
BOOLEAN = {"boolean": None}


def select(options, key, multiple=False):
    return {
        "select": {
            "options": options,
            "translation_key": key,
            "multiple": multiple,
            "mode": "dropdown",
        }
    }


F = {
    "config_entry_id": (
        {"config_entry": {"integration": "hevy"}},
        False,
        None,
        ("Account", "The Hevy account to use. Optional if only one is configured."),
        ("Konto", "Hevy-kontoen som skal brukes. Valgfri hvis bare én er satt opp."),
    ),
    "page": (
        num(1),
        False,
        1,
        ("Page", "Page number (1 or greater)."),
        ("Side", "Sidenummer (1 eller høyere)."),
    ),
    "page_size": (
        num(1, 10),
        False,
        5,
        ("Page size", "Number of items per page (max 10)."),
        ("Sidestørrelse", "Antall elementer per side (maks 10)."),
    ),
    "template_page_size": (
        num(1, 100),
        False,
        50,
        ("Page size", "Number of items per page (max 100)."),
        ("Sidestørrelse", "Antall elementer per side (maks 100)."),
    ),
    "workout_id": (
        TEXT,
        True,
        "b459cba5-cd6d-463c-abd6-54f8eafcadcb",
        ("Workout ID", "The ID of the workout."),
        ("Økt-ID", "ID-en til treningsøkten."),
    ),
    "since": (
        DATETIME,
        False,
        "2024-01-01 00:00:00",
        ("Since", "Return events after this time."),
        ("Siden", "Returner hendelser etter dette tidspunktet."),
    ),
    "title": (
        TEXT,
        True,
        "Morning Workout",
        ("Title", "Title."),
        ("Tittel", "Tittel."),
    ),
    "description": (
        TEXT,
        False,
        "Pushed myself to the limit today!",
        ("Description", "Workout description."),
        ("Beskrivelse", "Beskrivelse av økten."),
    ),
    "start_time": (
        DATETIME,
        True,
        "2024-08-14 12:00:00",
        ("Start time", "When the workout started."),
        ("Starttid", "Når økten startet."),
    ),
    "end_time": (
        DATETIME,
        True,
        "2024-08-14 13:00:00",
        ("End time", "When the workout ended."),
        ("Sluttid", "Når økten sluttet."),
    ),
    "is_private": (
        BOOLEAN,
        False,
        False,
        ("Private", "Hide the workout from other users."),
        ("Privat", "Skjul økten for andre brukere."),
    ),
    "workout_exercises": (
        OBJECT,
        True,
        '[{"exercise_template_id": "D04AC939", "superset_id": null, "notes": "", '
        '"sets": [{"type": "normal", "weight_kg": 100, "reps": 10, "rpe": 8}]}]',
        (
            "Exercises",
            "List of exercises. Each has exercise_template_id, optional "
            "superset_id and notes, and sets (type, weight_kg, reps, "
            "distance_meters, duration_seconds, rpe, custom_metric).",
        ),
        (
            "Øvelser",
            "Liste med øvelser. Hver har exercise_template_id, valgfri "
            "superset_id og notes, og sets (type, weight_kg, reps, "
            "distance_meters, duration_seconds, rpe, custom_metric).",
        ),
    ),
    "routine_id": (
        TEXT,
        True,
        "b459cba5-cd6d-463c-abd6-54f8eafcadcb",
        ("Routine ID", "The ID of the routine."),
        ("Rutine-ID", "ID-en til rutinen."),
    ),
    "folder_id_optional": (
        num(0),
        False,
        42,
        ("Folder ID", "Routine folder to put the routine in."),
        ("Mappe-ID", "Rutinemappen rutinen skal legges i."),
    ),
    "folder_id": (
        num(0),
        True,
        42,
        ("Folder ID", "The ID of the routine folder."),
        ("Mappe-ID", "ID-en til rutinemappen."),
    ),
    "notes": (
        TEXT,
        False,
        "Focus on form",
        ("Notes", "Routine notes."),
        ("Notater", "Notater for rutinen."),
    ),
    "routine_exercises": (
        OBJECT,
        True,
        '[{"exercise_template_id": "D04AC939", "rest_seconds": 90, '
        '"sets": [{"type": "normal", "weight_kg": 100, "rep_range": {"start": 8, "end": 12}}]}]',
        (
            "Exercises",
            "List of exercises. Each has exercise_template_id, optional "
            "superset_id, rest_seconds and notes, and sets (type, weight_kg, "
            "reps, rep_range, distance_meters, duration_seconds, custom_metric).",
        ),
        (
            "Øvelser",
            "Liste med øvelser. Hver har exercise_template_id, valgfri "
            "superset_id, rest_seconds og notes, og sets (type, weight_kg, "
            "reps, rep_range, distance_meters, duration_seconds, custom_metric).",
        ),
    ),
    "exercise_template_id": (
        TEXT,
        True,
        "D04AC939",
        ("Exercise template ID", "The ID of the exercise template."),
        ("Øvelsesmal-ID", "ID-en til øvelsesmalen."),
    ),
    "exercise_type": (
        select(EXERCISE_TYPES, "exercise_type"),
        True,
        "weight_reps",
        ("Exercise type", "How the exercise is logged."),
        ("Øvelsestype", "Hvordan øvelsen logges."),
    ),
    "equipment_category": (
        select(EQUIPMENT_CATEGORIES, "equipment_category"),
        True,
        "barbell",
        ("Equipment", "Equipment category."),
        ("Utstyr", "Utstyrskategori."),
    ),
    "muscle_group": (
        select(MUSCLE_GROUPS, "muscle_group"),
        True,
        "chest",
        ("Primary muscle group", "Primary muscle group."),
        ("Primær muskelgruppe", "Primær muskelgruppe."),
    ),
    "other_muscles": (
        select(MUSCLE_GROUPS, "muscle_group", multiple=True),
        False,
        None,
        ("Other muscles", "Secondary muscle groups."),
        ("Andre muskler", "Sekundære muskelgrupper."),
    ),
    "start_date": (
        DATETIME,
        False,
        "2024-01-01 00:00:00",
        ("Start", "Only include history after this time."),
        ("Start", "Ta bare med historikk etter dette tidspunktet."),
    ),
    "end_date": (
        DATETIME,
        False,
        "2024-12-31 23:59:59",
        ("End", "Only include history before this time."),
        ("Slutt", "Ta bare med historikk før dette tidspunktet."),
    ),
    "date": (
        DATE,
        True,
        "2024-08-14",
        ("Date", "Date of the measurement."),
        ("Dato", "Dato for målingen."),
    ),
}

MEASUREMENTS = {
    "weight_kg": ("Weight", "Vekt", "kg"),
    "lean_mass_kg": ("Lean mass", "Fettfri masse", "kg"),
    "fat_percent": ("Body fat", "Kroppsfett", "%"),
    "neck_cm": ("Neck", "Nakke", "cm"),
    "shoulder_cm": ("Shoulders", "Skuldre", "cm"),
    "chest_cm": ("Chest", "Bryst", "cm"),
    "left_bicep_cm": ("Left bicep", "Venstre biceps", "cm"),
    "right_bicep_cm": ("Right bicep", "Høyre biceps", "cm"),
    "left_forearm_cm": ("Left forearm", "Venstre underarm", "cm"),
    "right_forearm_cm": ("Right forearm", "Høyre underarm", "cm"),
    "abdomen": ("Abdomen", "Mage", "cm"),
    "waist": ("Waist", "Midje", "cm"),
    "hips": ("Hips", "Hofter", "cm"),
    "left_thigh": ("Left thigh", "Venstre lår", "cm"),
    "right_thigh": ("Right thigh", "Høyre lår", "cm"),
    "left_calf": ("Left calf", "Venstre legg", "cm"),
    "right_calf": ("Right calf", "Høyre legg", "cm"),
}
for key, (en, nb, unit) in MEASUREMENTS.items():
    F[key] = (
        num(0, step=0.1, unit=unit),
        False,
        None,
        (en, f"{en} ({unit})."),
        (nb, f"{nb} ({unit})."),
    )

MEASUREMENT_KEYS = list(MEASUREMENTS)

# ------------------------------------------------------------------- services
# name: (fields [(field_name, field_def_key)], icon, (en name, desc), (nb name, desc))


def fl(*names):
    return [(n.split("=")[0], n.split("=")[-1]) for n in names]


SERVICES = {
    "get_user_info": (
        fl(),
        "mdi:account",
        ("Get user info", "Get the Hevy user profile."),
        ("Hent brukerinfo", "Hent Hevy-brukerprofilen."),
    ),
    "get_workouts": (
        fl("page", "page_size"),
        "mdi:dumbbell",
        ("Get workouts", "Get a paginated list of workouts, newest first."),
        ("Hent økter", "Hent en sidevis liste over treningsøkter, nyeste først."),
    ),
    "get_workout": (
        fl("workout_id"),
        "mdi:dumbbell",
        ("Get workout", "Get the complete details of a single workout."),
        ("Hent økt", "Hent alle detaljer for én treningsøkt."),
    ),
    "get_workout_count": (
        fl(),
        "mdi:counter",
        ("Get workout count", "Get the total number of workouts on the account."),
        ("Hent antall økter", "Hent totalt antall treningsøkter på kontoen."),
    ),
    "get_workout_events": (
        fl("since", "page", "page_size"),
        "mdi:history",
        (
            "Get workout events",
            "Get workouts updated or deleted since a given time, newest first.",
        ),
        (
            "Hent økthendelser",
            "Hent økter som er endret eller slettet siden et gitt tidspunkt.",
        ),
    ),
    "create_workout": (
        fl(
            "title",
            "description",
            "start_time",
            "end_time",
            "is_private",
            "exercises=workout_exercises",
        ),
        "mdi:plus-circle",
        ("Create workout", "Log a new workout in Hevy."),
        ("Opprett økt", "Logg en ny treningsøkt i Hevy."),
    ),
    "update_workout": (
        fl(
            "workout_id",
            "title",
            "description",
            "start_time",
            "end_time",
            "is_private",
            "exercises=workout_exercises",
        ),
        "mdi:pencil",
        ("Update workout", "Replace an existing workout."),
        ("Oppdater økt", "Erstatt en eksisterende treningsøkt."),
    ),
    "get_routines": (
        fl("page", "page_size"),
        "mdi:clipboard-list",
        ("Get routines", "Get a paginated list of routines."),
        ("Hent rutiner", "Hent en sidevis liste over rutiner."),
    ),
    "get_routine": (
        fl("routine_id"),
        "mdi:clipboard-list",
        ("Get routine", "Get a routine by ID."),
        ("Hent rutine", "Hent en rutine etter ID."),
    ),
    "create_routine": (
        fl(
            "title",
            "folder_id=folder_id_optional",
            "notes",
            "exercises=routine_exercises",
        ),
        "mdi:clipboard-plus",
        ("Create routine", "Create a new routine."),
        ("Opprett rutine", "Opprett en ny rutine."),
    ),
    "update_routine": (
        fl("routine_id", "title", "notes", "exercises=routine_exercises"),
        "mdi:clipboard-edit",
        ("Update routine", "Replace an existing routine."),
        ("Oppdater rutine", "Erstatt en eksisterende rutine."),
    ),
    "get_routine_folders": (
        fl("page", "page_size"),
        "mdi:folder-multiple",
        ("Get routine folders", "Get a paginated list of routine folders."),
        ("Hent rutinemapper", "Hent en sidevis liste over rutinemapper."),
    ),
    "get_routine_folder": (
        fl("folder_id"),
        "mdi:folder",
        ("Get routine folder", "Get a routine folder by ID."),
        ("Hent rutinemappe", "Hent en rutinemappe etter ID."),
    ),
    "create_routine_folder": (
        fl("title"),
        "mdi:folder-plus",
        ("Create routine folder", "Create a new routine folder (placed first)."),
        ("Opprett rutinemappe", "Opprett en ny rutinemappe (plasseres først)."),
    ),
    "get_exercise_templates": (
        fl("page", "page_size=template_page_size"),
        "mdi:weight-lifter",
        ("Get exercise templates", "Get a paginated list of exercise templates."),
        ("Hent øvelsesmaler", "Hent en sidevis liste over øvelsesmaler."),
    ),
    "get_exercise_template": (
        fl("exercise_template_id"),
        "mdi:weight-lifter",
        ("Get exercise template", "Get a single exercise template by ID."),
        ("Hent øvelsesmal", "Hent én øvelsesmal etter ID."),
    ),
    "create_exercise_template": (
        fl(
            "title",
            "exercise_type",
            "equipment_category",
            "muscle_group",
            "other_muscles",
        ),
        "mdi:plus-box",
        ("Create custom exercise", "Create a new custom exercise template."),
        ("Opprett egen øvelse", "Opprett en ny egendefinert øvelsesmal."),
    ),
    "get_exercise_history": (
        fl("exercise_template_id", "start_date", "end_date"),
        "mdi:chart-line",
        ("Get exercise history", "Get logged sets for an exercise template."),
        ("Hent øvelseshistorikk", "Hent loggede sett for en øvelsesmal."),
    ),
    "get_body_measurements": (
        fl("page", "page_size"),
        "mdi:human",
        ("Get body measurements", "Get a paginated list of body measurements."),
        ("Hent kroppsmål", "Hent en sidevis liste over kroppsmål."),
    ),
    "get_body_measurement": (
        fl("date"),
        "mdi:human",
        ("Get body measurement", "Get the body measurement for a date."),
        ("Hent kroppsmål for dato", "Hent kroppsmålet for en dato."),
    ),
    "create_body_measurement": (
        fl("date", *MEASUREMENT_KEYS),
        "mdi:human-male-height",
        (
            "Create body measurement",
            "Create a body measurement for a date (fails if one exists).",
        ),
        (
            "Opprett kroppsmål",
            "Opprett et kroppsmål for en dato (feiler hvis det finnes fra før).",
        ),
    ),
    "update_body_measurement": (
        fl("date", *MEASUREMENT_KEYS),
        "mdi:human-male-height",
        (
            "Update body measurement",
            "Overwrite the body measurement for a date. Omitted fields are cleared.",
        ),
        (
            "Oppdater kroppsmål",
            "Overskriv kroppsmålet for en dato. Felt som utelates blir tømt.",
        ),
    ),
}

# ------------------------------------------------------------- entity names

SENSORS = {
    "workout_count": ("Workouts", "Økter", "mdi:counter"),
    "last_workout": ("Last workout", "Siste økt", "mdi:dumbbell"),
    "last_workout_title": (
        "Last workout title",
        "Siste økt tittel",
        "mdi:format-title",
    ),
    "last_workout_duration": (
        "Last workout duration",
        "Siste økt varighet",
        "mdi:timer-outline",
    ),
    "last_workout_volume": ("Last workout volume", "Siste økt volum", "mdi:weight"),
    "last_workout_sets": (
        "Last workout sets",
        "Siste økt sett",
        "mdi:format-list-numbered",
    ),
    "workouts_this_week": (
        "Workouts this week",
        "Økter denne uken",
        "mdi:calendar-week",
    ),
    "volume_this_week": ("Volume this week", "Volum denne uken", "mdi:weight"),
    "workouts_last_7_days": (
        "Workouts last 7 days",
        "Økter siste 7 dager",
        "mdi:calendar-range",
    ),
    "workouts_last_30_days": (
        "Workouts last 30 days",
        "Økter siste 30 dager",
        "mdi:calendar-month",
    ),
    "routines": ("Routines", "Rutiner", "mdi:clipboard-list"),
    "routine_folders": ("Routine folders", "Rutinemapper", "mdi:folder-multiple"),
    "body_measurement_date": (
        "Last body measurement",
        "Siste kroppsmåling",
        "mdi:calendar-check",
    ),
    "weight": ("Weight", "Vekt", "mdi:scale-bathroom"),
    "lean_mass": ("Lean mass", "Fettfri masse", "mdi:arm-flex"),
    "fat_percent": ("Body fat", "Kroppsfett", "mdi:percent"),
}
EXERCISE_SENSORS = {
    "exercise_max_weight": ("Max weight", "Maks vekt", "mdi:weight-kilogram"),
    "exercise_estimated_1rm": ("Estimated 1RM", "Estimert 1RM", "mdi:trophy"),
    "exercise_best_set": ("Best set", "Beste sett", "mdi:star"),
    "exercise_last_volume": ("Last volume", "Siste volum", "mdi:weight"),
    "exercise_last_performed": ("Last performed", "Sist utført", "mdi:calendar-clock"),
    "exercise_max_reps": ("Max reps", "Maks repetisjoner", "mdi:repeat"),
    "exercise_workout_count": ("Workouts", "Økter", "mdi:counter"),
    "exercise_total_sets": (
        "Total sets",
        "Totalt antall sett",
        "mdi:format-list-numbered",
    ),
    "exercise_total_reps": ("Total reps", "Totalt antall repetisjoner", "mdi:repeat"),
    "exercise_total_volume": ("Total volume", "Totalt volum", "mdi:weight"),
    "exercise_last_sets": ("Last sets", "Sett siste økt", "mdi:format-list-numbered"),
    "exercise_last_reps": ("Last reps", "Repetisjoner siste økt", "mdi:repeat"),
    "exercise_last_top_weight": (
        "Last top weight",
        "Tyngste vekt siste økt",
        "mdi:weight-kilogram",
    ),
    "exercise_max_distance": (
        "Longest distance",
        "Lengste distanse",
        "mdi:map-marker-distance",
    ),
    "exercise_total_distance": (
        "Total distance",
        "Total distanse",
        "mdi:map-marker-distance",
    ),
    "exercise_max_duration": (
        "Longest duration",
        "Lengste varighet",
        "mdi:timer-outline",
    ),
    "exercise_total_duration": ("Total duration", "Total varighet", "mdi:timer-sand"),
    "routine_last_volume": ("Last volume", "Siste volum", "mdi:weight"),
    "routine_previous_volume": ("Previous volume", "Forrige volum", "mdi:weight"),
    "routine_volume_change": ("Volume change", "Volumendring", "mdi:trending-up"),
    "routine_last_performed": ("Last performed", "Sist utført", "mdi:calendar-clock"),
    "routine_workout_count": ("Workouts", "Økter", "mdi:counter"),
    "routine_last_duration": (
        "Last duration",
        "Varighet siste økt",
        "mdi:timer-outline",
    ),
}

for key, (en, nb, _unit) in MEASUREMENTS.items():
    if key.endswith("_cm") or _unit == "cm":
        SENSORS[key.removesuffix("_cm")] = (en, nb, "mdi:tape-measure")
SENSORS |= EXERCISE_SENSORS

# ------------------------------------------------------------ select labels

SELECT_LABELS = {
    "exercise_type": {
        "weight_reps": ("Weight & reps", "Vekt og repetisjoner"),
        "reps_only": ("Reps only", "Kun repetisjoner"),
        "bodyweight_reps": ("Bodyweight reps", "Kroppsvekt-repetisjoner"),
        "bodyweight_assisted_reps": (
            "Assisted bodyweight reps",
            "Assisterte kroppsvekt-repetisjoner",
        ),
        "duration": ("Duration", "Varighet"),
        "weight_duration": ("Weight & duration", "Vekt og varighet"),
        "distance_duration": ("Distance & duration", "Distanse og varighet"),
        "short_distance_weight": ("Short distance & weight", "Kort distanse og vekt"),
    },
    "equipment_category": {
        "none": ("None", "Ingen"),
        "barbell": ("Barbell", "Vektstang"),
        "dumbbell": ("Dumbbell", "Manual"),
        "kettlebell": ("Kettlebell", "Kettlebell"),
        "machine": ("Machine", "Maskin"),
        "plate": ("Plate", "Vektskive"),
        "resistance_band": ("Resistance band", "Strikk"),
        "suspension": ("Suspension", "Slynge"),
        "other": ("Other", "Annet"),
    },
    "muscle_group": {
        "abdominals": ("Abdominals", "Mage"),
        "shoulders": ("Shoulders", "Skuldre"),
        "biceps": ("Biceps", "Biceps"),
        "triceps": ("Triceps", "Triceps"),
        "forearms": ("Forearms", "Underarmer"),
        "quadriceps": ("Quadriceps", "Forside lår"),
        "hamstrings": ("Hamstrings", "Bakside lår"),
        "calves": ("Calves", "Legger"),
        "glutes": ("Glutes", "Sete"),
        "abductors": ("Abductors", "Abduktorer"),
        "adductors": ("Adductors", "Adduktorer"),
        "lats": ("Lats", "Latissimus"),
        "upper_back": ("Upper back", "Øvre rygg"),
        "traps": ("Traps", "Trapezius"),
        "lower_back": ("Lower back", "Korsrygg"),
        "chest": ("Chest", "Bryst"),
        "cardio": ("Cardio", "Kondisjon"),
        "neck": ("Neck", "Nakke"),
        "full_body": ("Full body", "Hele kroppen"),
        "other": ("Other", "Annet"),
    },
}
assert set(SELECT_LABELS["exercise_type"]) == set(EXERCISE_TYPES)
assert set(SELECT_LABELS["equipment_category"]) == set(EQUIPMENT_CATEGORIES)
assert set(SELECT_LABELS["muscle_group"]) == set(MUSCLE_GROUPS)
_ = SET_TYPES

# ------------------------------------------------------------ static strings

CONFIG = {
    "en": {
        "step": {
            "user": {
                "title": "Connect to Hevy",
                "description": "Enter your Hevy API key. It requires Hevy Pro and "
                "is created at [Hevy developer settings]({url}).",
                "data": {"api_key": "API key"},
                "data_description": {"api_key": "Your personal Hevy API key."},
            },
            "reauth_confirm": {
                "title": "Re-authenticate Hevy",
                "description": "The Hevy API key was rejected. Enter a new key "
                "from [Hevy developer settings]({url}).",
                "data": {"api_key": "API key"},
                "data_description": {"api_key": "Your personal Hevy API key."},
            },
        },
        "error": {
            "invalid_auth": "Invalid API key.",
            "cannot_connect": "Failed to connect to Hevy.",
            "unknown": "Unexpected error.",
        },
        "abort": {
            "already_configured": "This Hevy account is already configured.",
            "reauth_successful": "Re-authentication was successful.",
            "wrong_account": "The API key belongs to a different Hevy account.",
        },
    },
    "nb": {
        "step": {
            "user": {
                "title": "Koble til Hevy",
                "description": "Skriv inn Hevy API-nøkkelen din. Den krever Hevy "
                "Pro og opprettes i [Hevy utviklerinnstillinger]({url}).",
                "data": {"api_key": "API-nøkkel"},
                "data_description": {"api_key": "Din personlige Hevy API-nøkkel."},
            },
            "reauth_confirm": {
                "title": "Autentiser Hevy på nytt",
                "description": "Hevy avviste API-nøkkelen. Skriv inn en ny nøkkel "
                "fra [Hevy utviklerinnstillinger]({url}).",
                "data": {"api_key": "API-nøkkel"},
                "data_description": {"api_key": "Din personlige Hevy API-nøkkel."},
            },
        },
        "error": {
            "invalid_auth": "Ugyldig API-nøkkel.",
            "cannot_connect": "Kunne ikke koble til Hevy.",
            "unknown": "Uventet feil.",
        },
        "abort": {
            "already_configured": "Denne Hevy-kontoen er allerede satt opp.",
            "reauth_successful": "Ny autentisering var vellykket.",
            "wrong_account": "API-nøkkelen tilhører en annen Hevy-konto.",
        },
    },
}

OPTIONS = {
    "en": {
        "step": {
            "init": {
                "title": "Hevy options",
                "data": {"scan_interval": "Update interval"},
                "data_description": {
                    "scan_interval": "How often to poll Hevy, in minutes."
                },
            }
        }
    },
    "nb": {
        "step": {
            "init": {
                "title": "Hevy-innstillinger",
                "data": {"scan_interval": "Oppdateringsintervall"},
                "data_description": {
                    "scan_interval": "Hvor ofte Hevy skal spørres, i minutter."
                },
            }
        }
    },
}

EXCEPTIONS = {
    "en": {
        "auth_failed": "Hevy rejected the API key.",
        "rate_limited": "Rate limited by Hevy. Try again later.",
        "update_failed": "Error fetching data from Hevy: {error}",
        "api_error": "Hevy API error: {error}",
        "not_found": "Not found in Hevy: {error}",
        "entry_not_found": "Hevy config entry {entry_id} not found.",
        "entry_not_loaded": "Hevy config entry {entry_id} is not loaded.",
        "entry_required": "Several Hevy accounts are configured; select one.",
        "no_entries": "No Hevy account is configured.",
    },
    "nb": {
        "auth_failed": "Hevy avviste API-nøkkelen.",
        "rate_limited": "Hevy begrenser antall forespørsler. Prøv igjen senere.",
        "update_failed": "Feil ved henting av data fra Hevy: {error}",
        "api_error": "Feil fra Hevy-API: {error}",
        "not_found": "Ikke funnet i Hevy: {error}",
        "entry_not_found": "Fant ikke Hevy-oppføringen {entry_id}.",
        "entry_not_loaded": "Hevy-oppføringen {entry_id} er ikke lastet.",
        "entry_required": "Flere Hevy-kontoer er satt opp; velg én.",
        "no_entries": "Ingen Hevy-konto er satt opp.",
    },
}


def build_services_yaml() -> dict:
    out = {}
    for name, (fields, _icon, _en, _nb) in SERVICES.items():
        svc_fields = {}
        for field_name, def_key in [("config_entry_id", "config_entry_id"), *fields]:
            selector, required, example, _fen, _fnb = F[def_key]
            entry = {"required": required}
            if example is not None:
                entry["example"] = example
            entry["selector"] = selector
            svc_fields[field_name] = entry
        out[name] = {"fields": svc_fields}
    return out


def build_strings(lang: str) -> dict:
    idx = 0 if lang == "en" else 1
    services = {}
    for name, (fields, _icon, en, nb) in SERVICES.items():
        sname, sdesc = (en, nb)[idx]
        services[name] = {
            "name": sname,
            "description": sdesc,
            "fields": {
                field_name: {
                    "name": F[def_key][3 + idx][0],
                    "description": F[def_key][3 + idx][1],
                }
                for field_name, def_key in [
                    ("config_entry_id", "config_entry_id"),
                    *fields,
                ]
            },
        }
    return {
        "config": CONFIG[lang],
        "options": OPTIONS[lang],
        "entity": {
            "sensor": {
                key: {"name": (en, nb)[idx]} for key, (en, nb, _i) in SENSORS.items()
            }
        },
        "exceptions": {k: {"message": v} for k, v in EXCEPTIONS[lang].items()},
        "selector": {
            key: {"options": {opt: labels[idx] for opt, labels in opts.items()}}
            for key, opts in SELECT_LABELS.items()
        },
        "services": services,
    }


def build_icons() -> dict:
    return {
        "entity": {
            "sensor": {
                key: {"default": icon}
                for key, (_en, _nb, icon) in SENSORS.items()
                if key not in ("last_workout",)
            }
            | {"last_workout": {"default": "mdi:dumbbell"}}
        },
        "services": {
            name: {"service": icon} for name, (_f, icon, _e, _n) in SERVICES.items()
        },
    }


def dump_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> None:
    class Dumper(yaml.SafeDumper):
        def ignore_aliases(self, data):
            return True

    Dumper.add_representer(
        type(None), lambda d, _: d.represent_scalar("tag:yaml.org,2002:null", "")
    )
    (ROOT / "services.yaml").write_text(
        "# Generated by script/gen_translations.py - do not edit by hand.\n"
        + yaml.dump(
            build_services_yaml(),
            Dumper=Dumper,
            sort_keys=False,
            allow_unicode=True,
            width=100,
        ),
        encoding="utf-8",
    )
    en = build_strings("en")
    dump_json(ROOT / "strings.json", en)
    dump_json(ROOT / "translations" / "en.json", en)
    dump_json(ROOT / "translations" / "nb.json", build_strings("nb"))
    dump_json(ROOT / "icons.json", build_icons())


if __name__ == "__main__":
    main()
