"""Tests for calendar, binary sensors and account-wide statistics sensors."""

from __future__ import annotations

from datetime import timedelta

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util


def _eid(hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str) -> str:
    eid = er.async_get(hass).async_get_entity_id(
        platform, "hevy", f"{entry.unique_id}_{key}"
    )
    assert eid is not None, key
    return eid


async def test_calendar_and_binary_sensors(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    hass_client,
) -> None:
    """Workouts show up in the calendar; today/this-week flags are set."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    calendar = _eid(hass, config_entry, "calendar", "workout_calendar")
    client = await hass_client()
    start = (dt_util.utcnow() - timedelta(days=60)).isoformat()
    end = dt_util.utcnow().isoformat()
    resp = await client.get(
        f"/api/calendars/{calendar}", params={"start": start, "end": end}
    )
    assert resp.status == 200
    events = await resp.json()
    # All three workouts, including the 40-day-old one (full history).
    assert [e["summary"] for e in events] == ["Old", "Pull", "Push"]
    assert (
        "Bench Press (Barbell): 2 sets (best 100 kg × 10)" in events[0]["description"]
    )
    assert "chest" in events[0]["description"]

    # The latest workout started 3 h ago -> worked out today, unless the test
    # runs just after local midnight.
    latest_start = dt_util.as_local(dt_util.utcnow() - timedelta(hours=3)).date()
    today = dt_util.as_local(dt_util.utcnow()).date()
    expected = "on" if latest_start == today else "off"
    assert (
        hass.states.get(
            _eid(hass, config_entry, "binary_sensor", "worked_out_today")
        ).state
        == expected
    )


async def test_account_statistics_sensors(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """Streak, muscle groups, weekly volume and next workout."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    streak = hass.states.get(_eid(hass, config_entry, "sensor", "current_streak"))
    # Workouts today-ish and 3 days ago: gap > 1 rest day, so the streak is 1.
    assert streak.state == "1"
    assert streak.attributes["longest_streak"] == 1

    muscles = hass.states.get(
        _eid(hass, config_entry, "sensor", "muscle_group_summary")
    )
    assert muscles.state == "chest"
    assert muscles.attributes["last_workout_secondary_groups"] == ["triceps"]
    assert muscles.attributes["days_since_last"]["chest"] in (0, 1)

    volume = hass.states.get(_eid(hass, config_entry, "sensor", "weekly_muscle_volume"))
    # Two workouts in the last 7 days, 1800 kg each, all chest.
    assert volume.state == "3600.0"
    assert volume.attributes["muscle_groups"] == {"chest": 3600.0}

    nxt = hass.states.get(_eid(hass, config_entry, "sensor", "next_workout"))
    # Only one routine exists, so it is also the next one.
    assert nxt.state == "Upper"
    assert nxt.attributes["rotation_total"] == 1
