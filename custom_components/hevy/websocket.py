"""Websocket API backing the Hevy live workout card."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
import uuid

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import JSON, HevyConnectionError, HevyError
from .const import DOMAIN, SET_TYPES
from .coordinator import HevyConfigEntry, HevyCoordinator
from .services import extract_workout

SESSION_STORAGE_VERSION = 1
DATA_SESSIONS = f"{DOMAIN}_sessions"

STATUS_ACTIVE = "active"
STATUS_SUBMITTING = "submitting"
STATUS_SUBMITTED = "submitted"
STATUS_FAILED = "failed"
STATUS_UNCERTAIN = "uncertain"

MEASUREMENTS = ("weight_kg", "reps", "duration_seconds", "distance_meters")


def session_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    """Persistent store for the active card session of an entry."""
    return Store(hass, SESSION_STORAGE_VERSION, f"{DOMAIN}.session.{entry_id}")


def _number(value: Any, integer: bool = False) -> float | int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return int(round(number)) if integer else number


def _sanitize_set(raw: Any) -> JSON:
    raw = raw if isinstance(raw, dict) else {}
    set_type = raw.get("type") if raw.get("type") in SET_TYPES else "normal"
    rpe = _number(raw.get("rpe"))
    return {
        "type": set_type,
        "weight_kg": _number(raw.get("weight_kg")),
        "reps": _number(raw.get("reps"), integer=True),
        "duration_seconds": _number(raw.get("duration_seconds"), integer=True),
        "distance_meters": _number(raw.get("distance_meters"), integer=True),
        "rpe": rpe if rpe in (6, 7, 7.5, 8, 8.5, 9, 9.5, 10) else None,
        "done": bool(raw.get("done")),
    }


def _sanitize_session(raw: dict[str, Any], previous: JSON | None) -> JSON:
    """Keep only known fields with sane types; server owns status/result."""
    exercises = []
    for ex in raw.get("exercises") or []:
        if not isinstance(ex, dict) or not ex.get("exercise_template_id"):
            continue
        exercises.append(
            {
                "key": str(ex.get("key") or uuid.uuid4().hex),
                "exercise_template_id": str(ex["exercise_template_id"]),
                "title": str(ex.get("title") or ""),
                "type": ex.get("type") if isinstance(ex.get("type"), str) else None,
                "notes": str(ex.get("notes") or ""),
                "superset_id": _number(ex.get("superset_id"), integer=True),
                "sets": [_sanitize_set(s) for s in ex.get("sets") or []],
            }
        )
    started = raw.get("started_at")
    if not isinstance(started, str) or dt_util.parse_datetime(started) is None:
        started = (previous or {}).get("started_at") or dt_util.utcnow().isoformat()
    return {
        "id": str(raw.get("id") or (previous or {}).get("id") or uuid.uuid4().hex),
        "title": str(raw.get("title") or "").strip()[:200] or "Workout",
        "description": str(raw.get("description") or ""),
        "routine_id": raw.get("routine_id")
        if isinstance(raw.get("routine_id"), str)
        else None,
        "is_private": bool(raw.get("is_private")),
        "started_at": started,
        "exercises": exercises,
        "status": STATUS_ACTIVE,
        "result": None,
        "updated_at": dt_util.utcnow().isoformat(),
    }


def build_workout_payload(session: JSON, end: datetime) -> JSON:
    """Hevy workout payload from the completed sets of a session."""
    exercises = []
    for ex in session.get("exercises") or []:
        sets = [
            {
                "type": s["type"],
                "weight_kg": s.get("weight_kg"),
                "reps": s.get("reps"),
                "distance_meters": s.get("distance_meters"),
                "duration_seconds": s.get("duration_seconds"),
                "rpe": s.get("rpe"),
                "custom_metric": None,
            }
            for s in ex.get("sets") or []
            if s.get("done") and any(s.get(k) is not None for k in MEASUREMENTS)
        ]
        if sets:
            exercises.append(
                {
                    "exercise_template_id": ex["exercise_template_id"],
                    "superset_id": ex.get("superset_id"),
                    "notes": ex.get("notes") or None,
                    "sets": sets,
                }
            )
    start = dt_util.parse_datetime(session["started_at"]) or end
    # Hevy needs a start before the end; keep at least one minute.
    start = min(start, end - timedelta(minutes=1))
    return {
        "title": session.get("title") or "Workout",
        "description": session.get("description") or None,
        "start_time": dt_util.as_utc(start).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_time": dt_util.as_utc(end).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "is_private": bool(session.get("is_private")),
        "exercises": exercises,
    }


class SessionManager:
    """Loads and saves the single active session per config entry."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self.hass = hass
        self._sessions: dict[str, JSON | None] = {}
        self._stores: dict[str, Store[dict[str, Any]]] = {}

    def _store(self, entry_id: str) -> Store[dict[str, Any]]:
        if entry_id not in self._stores:
            self._stores[entry_id] = session_store(self.hass, entry_id)
        return self._stores[entry_id]

    async def get(self, entry_id: str) -> JSON | None:
        """Return the stored session, if any."""
        if entry_id not in self._sessions:
            stored = await self._store(entry_id).async_load()
            session = (stored or {}).get("session")
            if session and session.get("status") == STATUS_SUBMITTING:
                # Home Assistant stopped mid-submission: the outcome is unknown.
                session["status"] = STATUS_UNCERTAIN
                session["result"] = {"error": "interrupted"}
            self._sessions[entry_id] = session
        return self._sessions[entry_id]

    async def set(self, entry_id: str, session: JSON | None) -> None:
        """Persist the session immediately (survives restarts)."""
        self._sessions[entry_id] = session
        await self._store(entry_id).async_save({"session": session})

    def forget(self, entry_id: str) -> None:
        """Drop cached state for a removed entry."""
        self._sessions.pop(entry_id, None)
        self._stores.pop(entry_id, None)


def _sessions(hass: HomeAssistant) -> SessionManager:
    if DATA_SESSIONS not in hass.data:
        hass.data[DATA_SESSIONS] = SessionManager(hass)
    return hass.data[DATA_SESSIONS]


def _entry(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> HevyConfigEntry | None:
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if (
        entry is None
        or entry.domain != DOMAIN
        or entry.state is not ConfigEntryState.LOADED
    ):
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "Hevy account not found"
        )
        return None
    return entry


def _account_stats(coordinator: HevyCoordinator) -> JSON:
    data = coordinator.data
    week_ago = dt_util.utcnow().timestamp() - 7 * 86400
    recent = 0
    for workout in data.workouts:
        started = dt_util.parse_datetime(workout.get("start_time") or "")
        if started and started.timestamp() >= week_ago:
            recent += 1
    return {
        "workout_count": data.workout_count,
        "last_7_days": recent,
        "streak": data.streak.current,
    }


@websocket_api.websocket_command({vol.Required("type"): "hevy/accounts"})
@callback
def ws_accounts(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """List loaded Hevy accounts."""
    accounts = []
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        coordinator: HevyCoordinator = entry.runtime_data
        user = coordinator.data.user if coordinator.data else {}
        accounts.append(
            {
                "entry_id": entry.entry_id,
                "title": entry.title,
                "name": user.get("name") or entry.title,
                "stats": _account_stats(coordinator) if coordinator.data else None,
            }
        )
    connection.send_result(msg["id"], {"accounts": accounts})


@websocket_api.websocket_command(
    {vol.Required("type"): "hevy/card_data", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def ws_card_data(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Routines, exercise catalog and previous sets for the card."""
    if (entry := _entry(hass, connection, msg)) is None:
        return
    coordinator = entry.runtime_data
    try:
        catalog = await coordinator.async_ensure_catalog()
    except HevyError:
        catalog = coordinator.data.templates
    data = coordinator.data
    folders = {f.get("id"): f.get("title") for f in data.routine_folders}
    routines = [
        {
            "id": r.get("id"),
            "title": r.get("title"),
            "folder_name": folders.get(r.get("folder_id")),
            "exercises": [
                {
                    "exercise_template_id": ex.get("exercise_template_id"),
                    "title": ex.get("title"),
                    "notes": ex.get("notes"),
                    "superset_id": ex.get("supersets_id", ex.get("superset_id")),
                    "type": (
                        catalog.get(ex.get("exercise_template_id") or "") or {}
                    ).get("type"),
                    "sets": [
                        {
                            "type": s.get("type") or "normal",
                            "weight_kg": s.get("weight_kg"),
                            "reps": s.get("reps")
                            if s.get("reps") is not None
                            else (s.get("rep_range") or {}).get("start"),
                            "duration_seconds": s.get("duration_seconds"),
                            "distance_meters": s.get("distance_meters"),
                        }
                        for s in ex.get("sets") or []
                    ],
                }
                for ex in r.get("exercises") or []
            ],
        }
        for r in data.routines
    ]
    connection.send_result(
        msg["id"],
        {
            "routines": routines,
            "next_routine_id": data.next_routine.routine_id
            if data.next_routine
            else None,
            "catalog": sorted(
                (
                    {
                        "id": tid,
                        "title": t.get("title"),
                        "type": t.get("type"),
                        "muscle_group": t.get("primary_muscle_group"),
                    }
                    for tid, t in catalog.items()
                ),
                key=lambda e: (e["title"] or "").casefold(),
            ),
            "last_sets": {
                tid: stats.last_workout_sets for tid, stats in data.exercises.items()
            },
            "stats": _account_stats(coordinator),
        },
    )


@websocket_api.websocket_command(
    {vol.Required("type"): "hevy/session/get", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def ws_session_get(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Return the saved session."""
    if _entry(hass, connection, msg) is None:
        return
    connection.send_result(
        msg["id"], {"session": await _sessions(hass).get(msg["entry_id"])}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hevy/session/save",
        vol.Required("entry_id"): str,
        vol.Required("session"): dict,
    }
)
@websocket_api.async_response
async def ws_session_save(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Save (create or replace) the active session."""
    if _entry(hass, connection, msg) is None:
        return
    manager = _sessions(hass)
    previous = await manager.get(msg["entry_id"])
    same = (
        previous
        if previous and previous.get("id") == msg["session"].get("id")
        else None
    )
    # Editing a workout whose submission is pending or uncertain could post it
    # twice; a new session (different id) or clearing is still allowed.
    if same and same.get("status") in (STATUS_SUBMITTING, STATUS_UNCERTAIN):
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_ALLOWED,
            "The workout is being submitted or its result is uncertain",
        )
        return
    session = _sanitize_session(msg["session"], same)
    await manager.set(msg["entry_id"], session)
    connection.send_result(msg["id"], {"session": session})


@websocket_api.websocket_command(
    {vol.Required("type"): "hevy/session/clear", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def ws_session_clear(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Discard the saved session."""
    if _entry(hass, connection, msg) is None:
        return
    await _sessions(hass).set(msg["entry_id"], None)
    connection.send_result(msg["id"], {"session": None})


@websocket_api.websocket_command(
    {vol.Required("type"): "hevy/session/finish", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def ws_session_finish(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Send the completed sets of the saved session to Hevy."""
    if (entry := _entry(hass, connection, msg)) is None:
        return
    manager = _sessions(hass)
    session = await manager.get(msg["entry_id"])
    if not session:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "No session")
        return
    if session.get("status") in (STATUS_SUBMITTING, STATUS_SUBMITTED):
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_ALLOWED, "Already submitted"
        )
        return
    payload = build_workout_payload(session, dt_util.utcnow())
    if not payload["exercises"]:
        connection.send_error(
            msg["id"], "no_completed_sets", "Check off at least one set first"
        )
        return

    coordinator: HevyCoordinator = entry.runtime_data
    session = {**session, "status": STATUS_SUBMITTING, "result": None}
    await manager.set(msg["entry_id"], session)
    try:
        response = await coordinator.client.create_workout(payload)
    except HevyConnectionError as err:
        session = {
            **session,
            "status": STATUS_UNCERTAIN,
            "result": {"error": str(err)},
        }
    except HevyError as err:
        session = {**session, "status": STATUS_FAILED, "result": {"error": str(err)}}
    else:
        workout = extract_workout(response)
        session = {
            **session,
            "status": STATUS_SUBMITTED,
            "result": {"workout_id": workout.get("id"), "title": workout.get("title")},
        }
        await coordinator.async_request_refresh()
    session["updated_at"] = dt_util.utcnow().isoformat()
    await manager.set(msg["entry_id"], session)
    connection.send_result(msg["id"], {"session": session})


@callback
def async_setup_websocket(hass: HomeAssistant) -> None:
    """Register websocket commands."""
    for command in (
        ws_accounts,
        ws_card_data,
        ws_session_get,
        ws_session_save,
        ws_session_clear,
        ws_session_finish,
    ):
        websocket_api.async_register_command(hass, command)


async def async_remove_session(hass: HomeAssistant, entry_id: str) -> None:
    """Delete the stored session of a removed entry."""
    _sessions(hass).forget(entry_id)
    await session_store(hass, entry_id).async_remove()
