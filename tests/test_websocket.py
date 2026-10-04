"""Tests for the live workout card backend."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.core import HomeAssistant

from .conftest import BASE


@pytest.fixture
async def ws(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    hass_ws_client,
):
    """Set up the integration and return a websocket client."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return await hass_ws_client(hass)


async def _call(client, **msg):
    await client.send_json_auto_id(msg)
    return await client.receive_json()


SESSION = {
    "id": "s1",
    "title": "Push",
    "started_at": "2026-10-03T07:00:00+00:00",
    "exercises": [
        {
            "key": "k1",
            "exercise_template_id": "D04AC939",
            "title": "Bench Press (Barbell)",
            "notes": "",
            "sets": [
                {"type": "warmup", "weight_kg": "60", "reps": "10", "done": True},
                {
                    "type": "normal",
                    "weight_kg": 100,
                    "reps": 5,
                    "rpe": 8.5,
                    "done": True,
                },
                {"type": "normal", "weight_kg": 100, "reps": 5, "done": False},
            ],
        },
        {
            "key": "k2",
            "exercise_template_id": "X",
            "title": "Skipped",
            "sets": [{"type": "bogus", "reps": 3, "done": False}],
        },
    ],
}


async def test_accounts_and_card_data(ws, config_entry: MockConfigEntry) -> None:
    """Accounts list and card data."""
    resp = await _call(ws, type="hevy/accounts")
    assert resp["success"]
    account = resp["result"]["accounts"][0]
    assert account["entry_id"] == config_entry.entry_id
    assert account["name"] == "John"
    assert account["stats"]["workout_count"] == 42
    assert account["stats"]["last_7_days"] == 2

    resp = await _call(ws, type="hevy/card_data", entry_id=config_entry.entry_id)
    result = resp["result"]
    assert result["routines"][0]["title"] == "Upper"
    assert result["next_routine_id"] == "r1"
    assert result["catalog"][0]["id"] == "D04AC939"
    assert result["last_sets"]["D04AC939"][0] == {
        "type": "normal",
        "weight_kg": 100,
        "reps": 10,
    }

    resp = await _call(ws, type="hevy/card_data", entry_id="missing")
    assert not resp["success"]
    assert resp["error"]["code"] == "not_found"


async def test_session_roundtrip(ws, config_entry: MockConfigEntry) -> None:
    """Save sanitizes, get returns, clear removes."""
    entry_id = config_entry.entry_id
    resp = await _call(ws, type="hevy/session/save", entry_id=entry_id, session=SESSION)
    session = resp["result"]["session"]
    assert session["status"] == "active"
    first_set = session["exercises"][0]["sets"][0]
    assert first_set["weight_kg"] == 60.0 and first_set["reps"] == 10
    assert session["exercises"][1]["sets"][0]["type"] == "normal"

    resp = await _call(ws, type="hevy/session/get", entry_id=entry_id)
    assert resp["result"]["session"]["id"] == "s1"

    await _call(ws, type="hevy/session/clear", entry_id=entry_id)
    resp = await _call(ws, type="hevy/session/get", entry_id=entry_id)
    assert resp["result"]["session"] is None


async def test_finish_sends_only_checked_sets(
    ws, config_entry: MockConfigEntry, mock_api: AiohttpClientMocker
) -> None:
    """Only completed sets are posted; status becomes submitted."""
    entry_id = config_entry.entry_id
    mock_api.post(
        f"{BASE}/workouts", json={"workout": [{"id": "w-new", "title": "Push"}]}
    )
    await _call(ws, type="hevy/session/save", entry_id=entry_id, session=SESSION)
    resp = await _call(ws, type="hevy/session/finish", entry_id=entry_id)
    session = resp["result"]["session"]
    assert session["status"] == "submitted"
    assert session["result"]["workout_id"] == "w-new"

    posts = [c for c in mock_api.mock_calls if c[0].upper() == "POST"]
    workout = posts[0][2]["workout"]
    assert workout["start_time"] == "2026-10-03T07:00:00Z"
    assert len(workout["exercises"]) == 1
    sets = workout["exercises"][0]["sets"]
    assert [s["type"] for s in sets] == ["warmup", "normal"]
    assert sets[1]["rpe"] == 8.5

    # A second finish is refused.
    resp = await _call(ws, type="hevy/session/finish", entry_id=entry_id)
    assert resp["error"]["code"] == "not_allowed"


async def test_finish_without_checked_sets(ws, config_entry: MockConfigEntry) -> None:
    """Nothing checked -> error, nothing posted."""
    entry_id = config_entry.entry_id
    session = {**SESSION, "exercises": [{**SESSION["exercises"][1]}]}
    await _call(ws, type="hevy/session/save", entry_id=entry_id, session=session)
    resp = await _call(ws, type="hevy/session/finish", entry_id=entry_id)
    assert resp["error"]["code"] == "no_completed_sets"


async def test_finish_failed_keeps_session(
    ws, config_entry: MockConfigEntry, mock_api: AiohttpClientMocker
) -> None:
    """API errors mark the session failed but keep it editable."""
    entry_id = config_entry.entry_id
    mock_api.post(f"{BASE}/workouts", status=400, json={"error": "Bad set"})
    await _call(ws, type="hevy/session/save", entry_id=entry_id, session=SESSION)
    resp = await _call(ws, type="hevy/session/finish", entry_id=entry_id)
    session = resp["result"]["session"]
    assert session["status"] == "failed"
    assert session["result"]["error"] == "Bad set"
    resp = await _call(ws, type="hevy/session/save", entry_id=entry_id, session=SESSION)
    assert resp["result"]["session"]["status"] == "active"


async def test_finish_uncertain_blocks_edits(
    ws, config_entry: MockConfigEntry, mock_api: AiohttpClientMocker
) -> None:
    """A timeout leaves the outcome uncertain; edits to it are refused."""
    entry_id = config_entry.entry_id
    mock_api.post(f"{BASE}/workouts", exc=TimeoutError())
    await _call(ws, type="hevy/session/save", entry_id=entry_id, session=SESSION)
    resp = await _call(ws, type="hevy/session/finish", entry_id=entry_id)
    assert resp["result"]["session"]["status"] == "uncertain"
    resp = await _call(ws, type="hevy/session/save", entry_id=entry_id, session=SESSION)
    assert resp["error"]["code"] == "not_allowed"
    # Starting a different session is fine.
    resp = await _call(
        ws, type="hevy/session/save", entry_id=entry_id, session={**SESSION, "id": "s2"}
    )
    assert resp["success"]


async def test_card_js_is_served(hass: HomeAssistant, ws, hass_client) -> None:
    """The card JS is available on the static path."""
    client = await hass_client()
    resp = await client.get("/hevy_static/hevy-workout-card.js")
    assert resp.status == 200
