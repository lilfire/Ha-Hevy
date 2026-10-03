"""Setup, sensor and coordinator tests."""

from __future__ import annotations

from datetime import timedelta

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hevy.const import EVENT_NEW_WORKOUT
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import BASE, make_workout


def calls_to(mock: AiohttpClientMocker, path: str) -> list:
    """URLs requested for a path."""
    return [c[1] for c in mock.mock_calls if c[1].path == path]


def entity_id(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    """Look up entity id by unique id."""
    registry = er.async_get(hass)
    eid = registry.async_get_entity_id("sensor", "hevy", f"{entry.unique_id}_{key}")
    assert eid is not None, key
    return eid


async def test_setup_and_sensors(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """Entry loads and sensors reflect API data."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED

    def state(key: str) -> str:
        return hass.states.get(entity_id(hass, config_entry, key)).state

    assert state("workout_count") == "42"
    assert state("last_workout_title") == "Push"
    assert state("last_workout_volume") == "1800.0"
    assert state("last_workout_sets") == "2"
    assert state("last_workout_duration") == "60.0"
    assert state("workouts_last_7_days") == "2"
    # w3 is 40 days old and outside the 30-day window.
    assert state("workouts_last_30_days") == "2"
    assert state("routines") == "1"
    assert state("routine_folders") == "1"
    assert state("weight") == "80.5"
    assert state("fat_percent") == "18.5"
    assert state("body_measurement_date") == "2024-02-01"

    last = hass.states.get(entity_id(hass, config_entry, "last_workout"))
    assert last.attributes["workout_id"] == "w1"
    assert last.attributes["exercises"][0]["title"] == "Bench Press (Barbell)"

    # Circumference sensors are disabled by default.
    registry = er.async_get(hass)
    waist = registry.async_get(entity_id(hass, config_entry, "waist"))
    assert waist.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """401 during setup triggers reauth."""
    aioclient_mock.get(f"{BASE}/user/info", status=401)
    config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert flows and flows[0]["context"]["source"] == "reauth"


async def test_server_error_retries(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """5xx during setup -> retry."""
    aioclient_mock.get(f"{BASE}/user/info", status=503)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_incremental_sync_fires_event(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """Second refresh uses /workouts/events and fires an event for new workouts."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data

    new = make_workout("w9", timedelta(minutes=5), "Legs")
    edited = make_workout("w2", timedelta(days=3), "Pull (edited)")
    mock_api.clear_requests()
    mock_api.get(f"{BASE}/user/info", json={"data": {"id": "x", "name": "John"}})
    mock_api.get(f"{BASE}/workouts/count", json={"workout_count": 43})
    mock_api.get(
        f"{BASE}/workouts/events",
        json={
            "page": 1,
            "page_count": 1,
            "events": [
                {"type": "updated", "workout": new},
                {"type": "updated", "workout": edited},
                {"type": "deleted", "id": "w1", "deleted_at": "2024-01-01T00:00:00Z"},
            ],
        },
    )
    for path, key in (
        ("routines", "routines"),
        ("routine_folders", "routine_folders"),
        ("body_measurements", "body_measurements"),
    ):
        mock_api.get(f"{BASE}/{path}", json={"page": 1, "page_count": 1, key: []})

    events = async_capture_events(hass, EVENT_NEW_WORKOUT)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert [e.data["workout_id"] for e in events] == ["w9"]
    assert events[0].data["volume_kg"] == 1800.0
    ids = [w["id"] for w in coordinator.data.workouts]
    assert ids == ["w9", "w2"]
    assert coordinator.data.workouts[1]["title"] == "Pull (edited)"
    assert not calls_to(mock_api, "/v1/workouts")
    since = calls_to(mock_api, "/v1/workouts/events")
    assert since and since[0].query["since"].endswith("Z")


async def test_body_measurement_checks_last_page(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """Newest measurement is found even when it is on the last page."""
    mock_api.clear_requests()
    mock_api.get(
        f"{BASE}/body_measurements?page=3",
        json={
            "page": 3,
            "page_count": 3,
            "body_measurements": [{"date": "2025-05-05", "weight_kg": 77}],
        },
    )
    mock_api.get(
        f"{BASE}/body_measurements",
        json={
            "page": 1,
            "page_count": 3,
            "body_measurements": [{"date": "2023-01-01", "weight_kg": 90}],
        },
    )
    for path, payload in (
        ("user/info", {"data": {"id": "x", "name": "John"}}),
        ("workouts/count", {"workout_count": 1}),
        ("workouts", {"page": 1, "page_count": 1, "workouts": []}),
        ("routines", {"page": 1, "page_count": 1, "routines": []}),
        ("routine_folders", {"page": 1, "page_count": 1, "routine_folders": []}),
    ):
        mock_api.get(f"{BASE}/{path}", json=payload)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.runtime_data.data.body_measurement["weight_kg"] == 77
