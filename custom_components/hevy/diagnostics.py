"""Diagnostics for Hevy."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from .coordinator import HevyConfigEntry

TO_REDACT = {CONF_API_KEY, "id", "name", "url", "unique_id", "title"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HevyConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data.data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "data": {
            "user": async_redact_data(data.user, TO_REDACT),
            "workout_count": data.workout_count,
            "workouts": len(data.workouts),
            "exercises": len(data.exercises),
            "routine_devices": len(data.routine_stats),
            "example_exercise": (
                asdict(next(iter(data.exercises.values()))) if data.exercises else None
            ),
            "latest_workout": data.latest_workout,
            "routines": len(data.routines),
            "routine_folders": len(data.routine_folders),
            "body_measurement": data.body_measurement,
        }
        if data
        else None,
    }
