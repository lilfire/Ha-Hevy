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
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

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
    assert ids == ["w9", "w2", "w3"]
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


async def test_exercise_and_routine_devices(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """Each exercise and routine gets its own device under the account."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    uid = config_entry.unique_id
    account = dev_reg.async_get_device({("hevy", uid)})
    bench = dev_reg.async_get_device({("hevy", f"{uid}_exercise_D04AC939")})
    routine = dev_reg.async_get_device({("hevy", f"{uid}_routine_r1")})
    assert bench is not None and routine is not None
    assert bench.name == "Bench Press (Barbell)"
    assert bench.model == "Chest"
    assert bench.via_device_id == account.id
    assert routine.via_device_id == account.id
    assert routine.model == "Routine – Plan"

    def bench_entity(key: str) -> str | None:
        return ent_reg.async_get_entity_id(
            "sensor", "hevy", f"{uid}_exercise_D04AC939_{key}"
        )

    # 3 workouts x 2 sets of 100 kg, newest 2 h ago.
    assert hass.states.get(bench_entity("max_weight")).state == "100.0"
    one_rm = hass.states.get(bench_entity("estimated_1rm"))
    assert one_rm.state == str(round(100 * (1 + 10 / 30), 1))
    assert one_rm.attributes["reps"] == 10
    assert hass.states.get(bench_entity("last_volume")).state == "1800.0"
    # Disabled by default; cardio sensors not created for a weight exercise.
    assert ent_reg.async_get(bench_entity("total_volume")).disabled_by is not None
    assert bench_entity("max_distance") is None

    routine_last = ent_reg.async_get_entity_id(
        "sensor", "hevy", f"{uid}_routine_r1_last_volume"
    )
    state = hass.states.get(routine_last)
    assert state.state == "1800.0"
    assert state.attributes["folder_name"] == "Plan"
    prev = ent_reg.async_get_entity_id(
        "sensor", "hevy", f"{uid}_routine_r1_previous_volume"
    )
    assert hass.states.get(prev).state == "1800.0"


async def test_new_exercise_and_deleted_routine(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """New exercises add devices without reload; deleted routines are removed."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    uid = config_entry.unique_id

    run = make_workout("w10", timedelta(minutes=10), "Run")
    run["routine_id"] = None
    run["exercises"] = [
        {
            "title": "Running",
            "exercise_template_id": "RUN1",
            "sets": [
                {"type": "normal", "distance_meters": 5000, "duration_seconds": 1500}
            ],
        }
    ]
    mock_api.clear_requests()
    for path, payload in (
        ("user/info", {"data": {"id": "x", "name": "John"}}),
        ("workouts/count", {"workout_count": 43}),
        (
            "workouts/events",
            {
                "page": 1,
                "page_count": 1,
                "events": [{"type": "updated", "workout": run}],
            },
        ),
        ("routines", {"page": 1, "page_count": 1, "routines": []}),
        ("routine_folders", {"page": 1, "page_count": 1, "routine_folders": []}),
        ("body_measurements", {"page": 1, "page_count": 1, "body_measurements": []}),
        ("exercise_templates", {"page": 1, "page_count": 1, "exercise_templates": []}),
    ):
        mock_api.get(f"{BASE}/{path}", json=payload)

    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    assert dev_reg.async_get_device({("hevy", f"{uid}_exercise_RUN1")}) is not None
    distance = ent_reg.async_get_entity_id(
        "sensor", "hevy", f"{uid}_exercise_RUN1_max_distance"
    )
    assert hass.states.get(distance).state == "5.0"  # suggested unit km
    assert (
        ent_reg.async_get_entity_id("sensor", "hevy", f"{uid}_exercise_RUN1_max_weight")
        is None
    )
    # Routine r1 no longer exists in Hevy -> device removed.
    assert dev_reg.async_get_device({("hevy", f"{uid}_routine_r1")}) is None


async def test_history_restored_from_store(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    hass_storage: dict,
) -> None:
    """With a cached history only the events endpoint is used."""
    hass_storage[f"hevy.{config_entry.entry_id}"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"hevy.{config_entry.entry_id}",
        "data": {
            "last_sync": "2026-01-01T00:00:00Z",
            "templates_fetched": dt_util.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "templates": {"D04AC939": {"title": "Bench", "type": "weight_reps"}},
            "workouts": [make_workout("cached", timedelta(days=1), "Cached")],
        },
    }
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert not calls_to(mock_api, "/v1/workouts")
    assert not calls_to(mock_api, "/v1/exercise_templates")
    assert calls_to(mock_api, "/v1/workouts/events")[0].query["since"] == (
        "2025-12-31T23:59:00Z"
    )
    data = config_entry.runtime_data.data
    assert [w["id"] for w in data.workouts] == ["cached"]
    assert data.exercises["D04AC939"].title == "Bench"
