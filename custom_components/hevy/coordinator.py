"""Data update coordinator for Hevy."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import JSON, HevyAuthError, HevyClient, HevyError, HevyRateLimitError
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_NEW_WORKOUT,
    MAX_HISTORY_PAGES,
    MAX_LIST_PAGES,
    MAX_PAGE_SIZE,
    MAX_TEMPLATE_PAGE_SIZE,
    MUSCLE_DUE_DAYS,
    STORAGE_VERSION,
    TEMPLATE_REFRESH_INTERVAL,
)
from .stats import (
    ExerciseStats,
    MuscleSummary,
    MuscleVolume,
    NextRoutine,
    RoutineStats,
    Streak,
    exercise_stats,
    muscle_summary,
    muscle_volume,
    next_routine,
    parse_time,
    routine_stats,
    streak,
    training_days,
    workout_duration_minutes,
    workout_set_count,
    workout_volume_kg,
)

_LOGGER = logging.getLogger(__name__)

type HevyConfigEntry = ConfigEntry[HevyCoordinator]

SAVE_DELAY = 10


def exercise_device_id(unique_id: str | None, template_id: str) -> str:
    """Device identifier for an exercise."""
    return f"{unique_id}_exercise_{template_id}"


def routine_device_id(unique_id: str | None, routine_id: str) -> str:
    """Device identifier for a routine."""
    return f"{unique_id}_routine_{routine_id}"


def store_for(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    """Return the persistent cache for a config entry."""
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")


@dataclass
class HevyData:
    """Snapshot of the Hevy account."""

    user: JSON
    workout_count: int | None
    # All known workouts, newest first.
    workouts: list[JSON] = field(default_factory=list)
    routines: list[JSON] = field(default_factory=list)
    routine_folders: list[JSON] = field(default_factory=list)
    body_measurement: JSON | None = None
    exercises: dict[str, ExerciseStats] = field(default_factory=dict)
    routine_stats: dict[str, RoutineStats] = field(default_factory=dict)
    streak: Streak = field(default_factory=Streak)
    muscles: MuscleSummary = field(default_factory=MuscleSummary)
    weekly_muscle_volume: MuscleVolume = field(default_factory=MuscleVolume)
    next_routine: NextRoutine | None = None
    templates: dict[str, JSON] = field(default_factory=dict)

    @property
    def latest_workout(self) -> JSON | None:
        """Most recent workout."""
        return self.workouts[0] if self.workouts else None


class HevyCoordinator(DataUpdateCoordinator[HevyData]):
    """Poll Hevy and keep a persistent cache of the workout history."""

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
        self._store = store_for(hass, entry.entry_id)
        self._workouts: dict[str, JSON] = {}
        self._templates: dict[str, JSON] = {}
        self._templates_fetched: datetime | None = None
        self._last_sync: datetime | None = None

    async def _async_setup(self) -> None:
        """Restore the cached workout history."""
        stored = await self._store.async_load()
        if not stored:
            return
        self._workouts = {
            w["id"]: w for w in stored.get("workouts") or [] if w.get("id")
        }
        self._templates = stored.get("templates") or {}
        self._templates_fetched = parse_time(stored.get("templates_fetched"))
        self._last_sync = parse_time(stored.get("last_sync"))

    def _data_to_store(self) -> dict[str, Any]:
        def _iso(value: datetime | None) -> str | None:
            return value.strftime("%Y-%m-%dT%H:%M:%SZ") if value else None

        return {
            "last_sync": _iso(self._last_sync),
            "templates_fetched": _iso(self._templates_fetched),
            "templates": self._templates,
            "workouts": list(self._workouts.values()),
        }

    async def _load_all_workouts(self) -> None:
        """Full load of the workout history."""
        workouts = await self.client.paginate(
            self.client.get_workouts, "workouts", MAX_PAGE_SIZE, MAX_HISTORY_PAGES
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
            MAX_HISTORY_PAGES,
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

    async def _refresh_templates(self) -> None:
        """Fetch the exercise template catalog when unknown exercises appear.

        The catalog is fetched at most once per TEMPLATE_REFRESH_INTERVAL.
        """
        used = {
            ex.get("exercise_template_id")
            for w in self._workouts.values()
            for ex in w.get("exercises") or []
        } - {None}
        if not used - set(self._templates):
            return
        if (
            self._templates_fetched is not None
            and dt_util.utcnow() - self._templates_fetched < TEMPLATE_REFRESH_INTERVAL
        ):
            return
        await self._fetch_templates()

    async def _fetch_templates(self) -> None:
        """Download the full exercise template catalog."""
        templates = await self.client.paginate(
            self.client.get_exercise_templates,
            "exercise_templates",
            MAX_TEMPLATE_PAGE_SIZE,
            MUSCLE_DUE_DAYS,
            MAX_LIST_PAGES,
        )
        self._templates = {
            t["id"]: {
                key: t.get(key)
                for key in (
                    "title",
                    "type",
                    "primary_muscle_group",
                    "secondary_muscle_groups",
                    "is_custom",
                )
            }
            for t in templates
            if t.get("id")
        }
        self._templates_fetched = dt_util.utcnow()

    async def _async_update_data(self) -> HevyData:
        """Fetch data from Hevy."""
        sync_started = dt_util.utcnow()
        first_sync = self._last_sync is None
        try:
            user = (await self.client.get_user_info()).get("data") or {}
            count = (await self.client.get_workout_count()).get("workout_count")

            new_workouts: list[JSON] = []
            if first_sync:
                await self._load_all_workouts()
            else:
                assert self._last_sync is not None
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
            try:
                await self._refresh_templates()
            except HevyError as err:
                if isinstance(err, HevyAuthError):
                    raise
                _LOGGER.debug("Could not fetch exercise templates: %s", err)
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

        self._last_sync = sync_started
        self._store.async_delay_save(self._data_to_store, SAVE_DELAY)

        workouts = sorted(
            self._workouts.values(),
            key=lambda w: w.get("start_time") or "",
            reverse=True,
        )

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

        now = dt_util.utcnow()
        today = dt_util.as_local(now).date()
        data = HevyData(
            user=user,
            workout_count=count,
            workouts=workouts,
            routines=routines,
            routine_folders=folders,
            body_measurement=measurement,
            exercises=exercise_stats(workouts, self._templates, now),
            routine_stats=routine_stats(workouts, routines, folders),
            streak=streak(training_days(workouts), today),
            muscles=muscle_summary(workouts, self._templates, today, MUSCLE_DUE_DAYS),
            weekly_muscle_volume=muscle_volume(
                workouts, self._templates, now - timedelta(days=7)
            ),
            next_routine=next_routine(workouts, routines),
            templates=self._templates,
        )
        self._remove_stale_devices(data)
        return data

    @property
    def templates(self) -> dict[str, JSON]:
        """Cached exercise template catalog keyed by id."""
        return self._templates

    async def async_ensure_catalog(self) -> dict[str, JSON]:
        """Make sure the exercise catalog is loaded (used by services/card)."""
        if not self._templates or self._templates_fetched is None:
            self._templates_fetched = None
            await self._fetch_templates()
            self._store.async_delay_save(self._data_to_store, SAVE_DELAY)
        return self._templates

    def _remove_stale_devices(self, data: HevyData) -> None:
        """Detach exercise/routine devices that no longer exist in Hevy."""
        entry = self.config_entry
        current = {exercise_device_id(entry.unique_id, t) for t in data.exercises}
        current |= {routine_device_id(entry.unique_id, r) for r in data.routine_stats}
        registry = dr.async_get(self.hass)
        prefixes = (f"{entry.unique_id}_exercise_", f"{entry.unique_id}_routine_")
        for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
            ids = {i for d, i in device.identifiers if d == DOMAIN}
            if any(i.startswith(prefixes) for i in ids) and not ids & current:
                registry.async_update_device(
                    device.id, remove_config_entry_id=entry.entry_id
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
