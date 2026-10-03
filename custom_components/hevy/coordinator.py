"""Data update coordinator for Hevy."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import JSON, HevyAuthError, HevyClient, HevyError, HevyRateLimitError
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_NEW_WORKOUT,
    MAX_LIST_PAGES,
    MAX_PAGE_SIZE,
    MAX_WORKOUT_PAGES,
    RECENT_WORKOUT_DAYS,
)

_LOGGER = logging.getLogger(__name__)

type HevyConfigEntry = ConfigEntry[HevyCoordinator]


def parse_time(value: Any) -> datetime | None:
    """Parse a Hevy ISO 8601 timestamp to an aware UTC datetime."""
    if not isinstance(value, str):
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return dt_util.as_utc(parsed)


def workout_volume_kg(workout: JSON) -> float:
    """Total volume (weight x reps) of a workout in kg."""
    total = 0.0
    for exercise in workout.get("exercises") or []:
        for workout_set in exercise.get("sets") or []:
            weight = workout_set.get("weight_kg")
            reps = workout_set.get("reps")
            if isinstance(weight, (int, float)) and isinstance(reps, (int, float)):
                total += weight * reps
    return round(total, 2)


def workout_set_count(workout: JSON) -> int:
    """Number of sets in a workout."""
    return sum(len(ex.get("sets") or []) for ex in workout.get("exercises") or [])


def workout_duration_minutes(workout: JSON) -> float | None:
    """Duration of a workout in minutes."""
    start = parse_time(workout.get("start_time"))
    end = parse_time(workout.get("end_time"))
    if start is None or end is None or end < start:
        return None
    return round((end - start).total_seconds() / 60, 1)


@dataclass
class HevyData:
    """Snapshot of the Hevy account."""

    user: JSON
    workout_count: int | None
    # Workouts within RECENT_WORKOUT_DAYS, newest first.
    workouts: list[JSON] = field(default_factory=list)
    routines: list[JSON] = field(default_factory=list)
    routine_folders: list[JSON] = field(default_factory=list)
    body_measurement: JSON | None = None

    @property
    def latest_workout(self) -> JSON | None:
        """Most recent workout."""
        return self.workouts[0] if self.workouts else None


class HevyCoordinator(DataUpdateCoordinator[HevyData]):
    """Poll Hevy and keep a local cache of recent workouts."""

    config_entry: HevyConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: HevyConfigEntry, client: HevyClient
    ) -> None:
        """Initialize the coordinator."""
        minutes = entry.options.get(CONF_SCAN_INTERVAL)
        interval = timedelta(minutes=minutes) if minutes else DEFAULT_SCAN_INTERVAL
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=interval,
        )
        self.client = client
        self._workouts: dict[str, JSON] = {}
        self._last_sync: datetime | None = None

    def _window_start(self) -> datetime:
        return dt_util.utcnow() - timedelta(days=RECENT_WORKOUT_DAYS)

    async def _load_recent_workouts(self) -> None:
        """Full load of workouts newer than the window start."""
        window_start = self._window_start()

        def _older_than_window(page: list[JSON]) -> bool:
            times = [parse_time(w.get("start_time")) for w in page]
            return any(t is not None and t < window_start for t in times)

        workouts = await self.client.paginate(
            self.client.get_workouts,
            "workouts",
            MAX_PAGE_SIZE,
            MAX_WORKOUT_PAGES,
            stop=_older_than_window,
        )
        self._workouts = {w["id"]: w for w in workouts if w.get("id")}

    async def _sync_workout_events(self, since: datetime) -> list[JSON]:
        """Apply updated/deleted events since ``since``; return new workouts."""
        events = await self.client.paginate(
            lambda page, size: self.client.get_workout_events(
                since=since.strftime("%Y-%m-%dT%H:%M:%SZ"), page=page, page_size=size
            ),
            "events",
            MAX_PAGE_SIZE,
            MAX_WORKOUT_PAGES,
        )
        new: list[JSON] = []
        # Events are newest first; apply oldest first so the newest wins.
        for event in reversed(events):
            if event.get("type") == "deleted" and event.get("id"):
                self._workouts.pop(event["id"], None)
            elif event.get("type") == "updated" and (workout := event.get("workout")):
                if (workout_id := workout.get("id")) is None:
                    continue
                if workout_id not in self._workouts:
                    new.append(workout)
                self._workouts[workout_id] = workout
        return new

    async def _async_update_data(self) -> HevyData:
        """Fetch data from Hevy."""
        sync_started = dt_util.utcnow()
        try:
            user = (await self.client.get_user_info()).get("data") or {}
            count = (await self.client.get_workout_count()).get("workout_count")

            new_workouts: list[JSON] = []
            if self._last_sync is None:
                await self._load_recent_workouts()
            else:
                # Overlap a minute to avoid missing events at the boundary.
                new_workouts = await self._sync_workout_events(
                    self._last_sync - timedelta(minutes=1)
                )

            routines = await self.client.paginate(
                self.client.get_routines, "routines", MAX_PAGE_SIZE, MAX_LIST_PAGES
            )
            folders = await self.client.paginate(
                self.client.get_routine_folders,
                "routine_folders",
                MAX_PAGE_SIZE,
                MAX_LIST_PAGES,
            )
            measurement = await self._latest_body_measurement()
        except HevyAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except HevyRateLimitError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="rate_limited",
                retry_after=err.retry_after,
            ) from err
        except HevyError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        first_sync = self._last_sync is None
        self._last_sync = sync_started

        window_start = self._window_start()
        workouts = [
            w
            for w in self._workouts.values()
            if (t := parse_time(w.get("start_time"))) is not None and t >= window_start
        ]
        workouts.sort(key=lambda w: w.get("start_time") or "", reverse=True)
        self._workouts = {w["id"]: w for w in workouts}

        if not first_sync:
            for workout in sorted(
                new_workouts, key=lambda w: w.get("start_time") or ""
            ):
                self.hass.bus.async_fire(
                    EVENT_NEW_WORKOUT,
                    {
                        "config_entry_id": self.config_entry.entry_id,
                        "workout_id": workout.get("id"),
                        "title": workout.get("title"),
                        "start_time": workout.get("start_time"),
                        "end_time": workout.get("end_time"),
                        "duration_minutes": workout_duration_minutes(workout),
                        "volume_kg": workout_volume_kg(workout),
                        "set_count": workout_set_count(workout),
                        "exercises": [
                            e.get("title") for e in workout.get("exercises") or []
                        ],
                    },
                )

        return HevyData(
            user=user,
            workout_count=count,
            workouts=workouts,
            routines=routines,
            routine_folders=folders,
            body_measurement=measurement,
        )

    async def _latest_body_measurement(self) -> JSON | None:
        """Return the newest body measurement.

        The API does not document the sort order, so the first and last page
        are both checked and the entry with the latest date wins.
        """
        first = await self.client.get_body_measurements(page=1, page_size=MAX_PAGE_SIZE)
        candidates: list[JSON] = list(first.get("body_measurements") or [])
        page_count = first.get("page_count")
        if isinstance(page_count, int) and page_count > 1:
            last = await self.client.get_body_measurements(
                page=page_count, page_size=MAX_PAGE_SIZE
            )
            candidates.extend(last.get("body_measurements") or [])
        candidates = [c for c in candidates if isinstance(c.get("date"), str)]
        if not candidates:
            return None
        return max(candidates, key=lambda c: c["date"])
