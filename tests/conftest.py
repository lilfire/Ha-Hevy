"""Fixtures for Hevy tests."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hevy.const import DOMAIN
from homeassistant.const import CONF_API_KEY
from homeassistant.util import dt as dt_util

BASE = "https://api.hevyapp.com/v1"
USER_ID = "9c465af3-de7d-42bc-9c7c-f0170396358b"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations."""


def iso(delta: timedelta) -> str:
    """UTC timestamp relative to now."""
    return (dt_util.utcnow() - delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_workout(
    workout_id: str, age: timedelta, title: str = "Push"
) -> dict[str, Any]:
    """Build a workout payload."""
    return {
        "id": workout_id,
        "title": title,
        "description": "",
        "routine_id": "r1",
        "start_time": iso(age + timedelta(hours=1)),
        "end_time": iso(age),
        "updated_at": iso(age),
        "created_at": iso(age),
        "exercises": [
            {
                "index": 0,
                "title": "Bench Press (Barbell)",
                "exercise_template_id": "D04AC939",
                "supersets_id": None,
                "sets": [
                    {"index": 0, "type": "normal", "weight_kg": 100, "reps": 10},
                    {"index": 1, "type": "normal", "weight_kg": 100, "reps": 8},
                ],
            }
        ],
    }


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="John",
        unique_id=USER_ID,
        data={CONF_API_KEY: "test-key"},
    )


@pytest.fixture
def mock_api(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Register default Hevy API responses."""
    aioclient_mock.get(
        f"{BASE}/user/info",
        json={
            "data": {"id": USER_ID, "name": "John", "url": "https://hevy.com/user/john"}
        },
    )
    aioclient_mock.get(f"{BASE}/workouts/count", json={"workout_count": 42})
    aioclient_mock.get(
        f"{BASE}/workouts",
        json={
            "page": 1,
            "page_count": 1,
            "workouts": [
                make_workout("w1", timedelta(hours=2), "Push"),
                make_workout("w2", timedelta(days=3), "Pull"),
                make_workout("w3", timedelta(days=40), "Old"),
            ],
        },
    )
    aioclient_mock.get(
        f"{BASE}/workouts/events",
        json={"page": 1, "page_count": 1, "events": []},
    )
    aioclient_mock.get(
        f"{BASE}/routines",
        json={
            "page": 1,
            "page_count": 1,
            "routines": [{"id": "r1", "title": "Upper", "folder_id": 1}],
        },
    )
    aioclient_mock.get(
        f"{BASE}/routine_folders",
        json={
            "page": 1,
            "page_count": 1,
            "routine_folders": [{"id": 1, "index": 0, "title": "Plan"}],
        },
    )
    aioclient_mock.get(
        f"{BASE}/body_measurements",
        json={
            "page": 1,
            "page_count": 1,
            "body_measurements": [
                {"date": "2024-01-01", "weight_kg": 82.0, "fat_percent": 20},
                {
                    "date": "2024-02-01",
                    "weight_kg": 80.5,
                    "fat_percent": 18.5,
                    "waist": 80,
                },
            ],
        },
    )
    return aioclient_mock
