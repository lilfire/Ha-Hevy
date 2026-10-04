"""Service tests."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
import voluptuous as vol

from custom_components.hevy.const import DOMAIN
from custom_components.hevy.services import SERVICES
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .conftest import BASE


@pytest.fixture
async def loaded(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Set up the integration."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


def calls(mock: AiohttpClientMocker, method: str, path: str) -> list:
    """Requests made to a path."""
    return [c for c in mock.mock_calls if c[0].upper() == method and c[1].path == path]


async def test_all_endpoints_registered(hass: HomeAssistant, loaded) -> None:
    """Every Hevy API v1 endpoint has a service."""
    assert len(SERVICES) == 22
    for name in SERVICES:
        assert hass.services.has_service(DOMAIN, name)


async def test_get_workouts(
    hass: HomeAssistant, loaded, mock_api: AiohttpClientMocker
) -> None:
    """GET services return the API response."""
    resp = await hass.services.async_call(
        DOMAIN,
        "get_workouts",
        {"page": 1, "page_size": 3},
        blocking=True,
        return_response=True,
    )
    assert resp["workouts"][0]["id"] == "w1"
    last = calls(mock_api, "GET", "/v1/workouts")[-1][1]
    assert last.query["pageSize"] == "3"


async def test_page_size_validated(hass: HomeAssistant, loaded) -> None:
    """Page size above the API max is rejected."""
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "get_workouts",
            {"page_size": 11},
            blocking=True,
            return_response=True,
        )


async def test_create_workout_payload(
    hass: HomeAssistant, loaded, mock_api: AiohttpClientMocker
) -> None:
    """Workout body is wrapped, defaults filled, times converted to UTC."""
    await hass.config.async_set_time_zone("Europe/Oslo")
    mock_api.post(f"{BASE}/workouts", json={"workout": [{"id": "new"}]})
    resp = await hass.services.async_call(
        DOMAIN,
        "create_workout",
        {
            "title": "Morning",
            "start_time": "2024-08-14 12:00:00",
            "end_time": "2024-08-14T13:00:00+02:00",
            "exercises": [
                {
                    "exercise_template_id": "D04AC939",
                    "sets": [{"weight_kg": 100, "reps": 10, "rpe": "8.5"}],
                }
            ],
        },
        blocking=True,
        return_response=True,
    )
    assert resp == {"workout": [{"id": "new"}]}
    body = calls(mock_api, "POST", "/v1/workouts")[0][2]
    workout = body["workout"]
    assert workout["start_time"] == "2024-08-14T10:00:00Z"
    assert workout["end_time"] == "2024-08-14T11:00:00Z"
    assert workout["is_private"] is False
    assert workout["description"] is None
    exercise = workout["exercises"][0]
    assert exercise["superset_id"] is None
    assert exercise["sets"][0] == {
        "type": "normal",
        "weight_kg": 100.0,
        "reps": 10,
        "distance_meters": None,
        "duration_seconds": None,
        "rpe": 8.5,
        "custom_metric": None,
    }
    dt_util.set_default_time_zone(dt_util.UTC)


async def test_invalid_rpe(hass: HomeAssistant, loaded) -> None:
    """RPE outside allowed values is rejected."""
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "create_workout",
            {
                "title": "x",
                "start_time": "2024-08-14 12:00:00",
                "end_time": "2024-08-14 13:00:00",
                "exercises": [
                    {"exercise_template_id": "A", "sets": [{"reps": 1, "rpe": 5}]}
                ],
            },
            blocking=True,
        )


async def test_create_routine_and_folder(
    hass: HomeAssistant, loaded, mock_api: AiohttpClientMocker
) -> None:
    """Routine and folder bodies match the API shape."""
    mock_api.post(f"{BASE}/routines", json={"routine": [{"id": "r9"}]})
    mock_api.post(f"{BASE}/routine_folders", json={"routine_folder": {"id": 5}})
    await hass.services.async_call(
        DOMAIN,
        "create_routine",
        {
            "title": "Legs",
            "folder_id": 5,
            "exercises": [
                {
                    "exercise_template_id": "X",
                    "rest_seconds": 90,
                    "sets": [{"rep_range": {"start": 8, "end": 12}}],
                }
            ],
        },
        blocking=True,
    )
    body = calls(mock_api, "POST", "/v1/routines")[0][2]
    assert body["routine"]["folder_id"] == 5
    assert body["routine"]["notes"] == ""
    assert body["routine"]["exercises"][0]["sets"][0]["rep_range"] == {
        "start": 8,
        "end": 12,
    }
    await hass.services.async_call(
        DOMAIN, "create_routine_folder", {"title": "Block 1"}, blocking=True
    )
    body = calls(mock_api, "POST", "/v1/routine_folders")[0][2]
    assert body == {"routine_folder": {"title": "Block 1"}}


async def test_exercise_template_and_history(
    hass: HomeAssistant, loaded, mock_api: AiohttpClientMocker
) -> None:
    """Custom exercise and history endpoints."""
    mock_api.post(f"{BASE}/exercise_templates", json={"id": "C1"})
    mock_api.get(
        f"{BASE}/exercise_history/D04AC939",
        json={"exercise_history": [{"weight_kg": 100, "reps": 5}]},
    )
    resp = await hass.services.async_call(
        DOMAIN,
        "create_exercise_template",
        {
            "title": "My curl",
            "exercise_type": "weight_reps",
            "equipment_category": "dumbbell",
            "muscle_group": "biceps",
        },
        blocking=True,
        return_response=True,
    )
    assert resp == {"id": "C1"}
    body = calls(mock_api, "POST", "/v1/exercise_templates")[0][2]
    assert body == {
        "exercise": {
            "title": "My curl",
            "exercise_type": "weight_reps",
            "equipment_category": "dumbbell",
            "muscle_group": "biceps",
            "other_muscles": [],
        }
    }
    resp = await hass.services.async_call(
        DOMAIN,
        "get_exercise_history",
        {"exercise_template_id": "D04AC939", "start_date": "2024-01-01T00:00:00Z"},
        blocking=True,
        return_response=True,
    )
    assert resp["exercise_history"][0]["reps"] == 5
    url = calls(mock_api, "GET", "/v1/exercise_history/D04AC939")[0][1]
    assert url.query["start_date"] == "2024-01-01T00:00:00Z"
    assert "end_date" not in url.query


async def test_body_measurement_services(
    hass: HomeAssistant, loaded, mock_api: AiohttpClientMocker
) -> None:
    """Create/update body measurement send only provided fields."""
    mock_api.post(f"{BASE}/body_measurements", text="")
    mock_api.put(f"{BASE}/body_measurements/2024-08-14", text="")
    await hass.services.async_call(
        DOMAIN,
        "create_body_measurement",
        {"date": "2024-08-14", "weight_kg": 80.5},
        blocking=True,
    )
    body = calls(mock_api, "POST", "/v1/body_measurements")[0][2]
    assert body == {"date": "2024-08-14", "weight_kg": 80.5}
    resp = await hass.services.async_call(
        DOMAIN,
        "update_body_measurement",
        {"date": "2024-08-14", "fat_percent": 18},
        blocking=True,
        return_response=True,
    )
    assert resp == {}
    body = calls(mock_api, "PUT", "/v1/body_measurements/2024-08-14")[0][2]
    assert body == {"fat_percent": 18.0}


async def test_not_found(
    hass: HomeAssistant, loaded, mock_api: AiohttpClientMocker
) -> None:
    """404 is a validation error."""
    mock_api.get(f"{BASE}/workouts/missing", status=404, json={"error": "Not found"})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "get_workout",
            {"workout_id": "missing"},
            blocking=True,
            return_response=True,
        )


async def test_unknown_entry(hass: HomeAssistant, loaded) -> None:
    """Unknown config_entry_id is rejected."""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "get_user_info",
            {"config_entry_id": "nope"},
            blocking=True,
            return_response=True,
        )


async def test_log_workout_by_name(
    hass: HomeAssistant, loaded, mock_api: AiohttpClientMocker
) -> None:
    """Names are matched case-insensitively; duration derives the start."""
    mock_api.post(
        f"{BASE}/workouts",
        json={"workout": [{"id": "new-id", "title": "Quick push"}]},
    )
    resp = await hass.services.async_call(
        DOMAIN,
        "log_workout",
        {
            "title": "Quick push",
            "end_time": "2026-10-03T08:00:00Z",
            "duration_minutes": 40,
            "exercises": [
                {
                    "name": "bench press (barbell)",
                    "sets": [{"weight_kg": 100, "reps": 5, "rpe": 9}],
                }
            ],
        },
        blocking=True,
        return_response=True,
    )
    assert resp == {"workout_id": "new-id", "title": "Quick push"}
    body = calls(mock_api, "POST", "/v1/workouts")[0][2]["workout"]
    assert body["start_time"] == "2026-10-03T07:20:00Z"
    assert body["end_time"] == "2026-10-03T08:00:00Z"
    assert body["exercises"][0]["exercise_template_id"] == "D04AC939"


async def test_log_workout_unknown_name_posts_nothing(
    hass: HomeAssistant, loaded, mock_api: AiohttpClientMocker
) -> None:
    """Unknown names raise with suggestions and nothing is sent."""
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "log_workout",
            {
                "title": "x",
                "duration_minutes": 30,
                "exercises": [{"name": "Bench Pres", "sets": [{"reps": 5}]}],
            },
            blocking=True,
        )
    assert err.value.translation_key == "unknown_exercise"
    assert "Bench Press (Barbell)" in err.value.translation_placeholders["suggestions"]
    assert not calls(mock_api, "POST", "/v1/workouts")


async def test_log_workout_requires_start_or_duration(
    hass: HomeAssistant, loaded
) -> None:
    """Without start_time or duration the call is rejected."""
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "log_workout",
            {
                "title": "x",
                "exercises": [{"exercise_template_id": "A", "sets": [{"reps": 5}]}],
            },
            blocking=True,
        )
    assert err.value.translation_key == "start_or_duration"


async def test_log_workout_set_needs_measurement(hass: HomeAssistant, loaded) -> None:
    """A set without any measurement fails validation."""
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "log_workout",
            {
                "title": "x",
                "duration_minutes": 30,
                "exercises": [
                    {"exercise_template_id": "A", "sets": [{"type": "normal"}]}
                ],
            },
            blocking=True,
        )


async def test_history_and_catalog(
    hass: HomeAssistant, loaded, mock_api: AiohttpClientMocker
) -> None:
    """History comes from the cache; catalog is sorted."""
    before = len(mock_api.mock_calls)
    resp = await hass.services.async_call(
        DOMAIN,
        "get_workout_history",
        {"days": 7},
        blocking=True,
        return_response=True,
    )
    assert len(mock_api.mock_calls) == before  # no API calls
    assert resp["summary"]["total_workouts"] == 2
    assert resp["summary"]["total_volume_kg"] == 3600.0
    assert resp["summary"]["avg_duration_minutes"] == 60.0
    assert resp["workouts"][0]["muscle_groups"] == ["chest"]

    catalog = await hass.services.async_call(
        DOMAIN, "get_exercise_catalog", {}, blocking=True, return_response=True
    )
    assert catalog["count"] == 1
    assert catalog["exercises"][0] == {
        "id": "D04AC939",
        "title": "Bench Press (Barbell)",
        "type": "weight_reps",
        "muscle_group": "chest",
        "is_custom": False,
    }
