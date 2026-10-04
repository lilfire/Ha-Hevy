"""Services exposing the full Hevy API."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import difflib
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .api import (
    JSON,
    HevyApiError,
    HevyAuthError,
    HevyClient,
    HevyError,
    HevyNotFoundError,
    HevyRateLimitError,
)
from .const import (
    BODY_MEASUREMENT_FIELDS,
    DOMAIN,
    EQUIPMENT_CATEGORIES,
    EXERCISE_TYPES,
    MAX_PAGE_SIZE,
    MAX_TEMPLATE_PAGE_SIZE,
    MUSCLE_GROUPS,
    RPE_VALUES,
    SET_TYPES,
)
from .coordinator import HevyConfigEntry, HevyCoordinator
from .stats import parse_time, workout_summary

ATTR_CONFIG_ENTRY_ID = "config_entry_id"

# --------------------------------------------------------------- validators


def _utc_string(value: Any) -> str:
    """Coerce a datetime (naive = HA local time) to Hevy's UTC format."""
    parsed = cv.datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())
    return dt_util.as_utc(parsed).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date_string(value: Any) -> str:
    """Coerce to YYYY-MM-DD."""
    parsed: date = cv.date(value)
    return parsed.isoformat()


def _rpe(value: Any) -> float | int | None:
    if value is None:
        return None
    number = float(value)
    if number not in RPE_VALUES:
        raise vol.Invalid(f"rpe must be one of {RPE_VALUES}")
    return int(number) if number.is_integer() else number


_OPT_FLOAT = vol.Any(None, vol.Coerce(float))
_OPT_INT = vol.Any(None, vol.Coerce(int))

PAGE = vol.All(vol.Coerce(int), vol.Range(min=1))
PAGE_SIZE = vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_PAGE_SIZE))
TEMPLATE_PAGE_SIZE = vol.All(
    vol.Coerce(int), vol.Range(min=1, max=MAX_TEMPLATE_PAGE_SIZE)
)

WORKOUT_SET_SCHEMA = vol.Schema(
    {
        vol.Optional("type", default="normal"): vol.In(SET_TYPES),
        vol.Optional("weight_kg", default=None): _OPT_FLOAT,
        vol.Optional("reps", default=None): _OPT_INT,
        vol.Optional("distance_meters", default=None): _OPT_INT,
        vol.Optional("duration_seconds", default=None): _OPT_INT,
        vol.Optional("rpe", default=None): _rpe,
        vol.Optional("custom_metric", default=None): _OPT_FLOAT,
    }
)

WORKOUT_EXERCISE_SCHEMA = vol.Schema(
    {
        vol.Required("exercise_template_id"): cv.string,
        vol.Optional("superset_id", default=None): _OPT_INT,
        vol.Optional("notes", default=None): vol.Any(None, cv.string),
        vol.Required("sets"): vol.All(cv.ensure_list, [WORKOUT_SET_SCHEMA]),
    }
)

REP_RANGE_SCHEMA = vol.Any(
    None,
    vol.Schema(
        {
            vol.Optional("start"): _OPT_INT,
            vol.Optional("end"): _OPT_INT,
        }
    ),
)

ROUTINE_SET_SCHEMA = vol.Schema(
    {
        vol.Optional("type", default="normal"): vol.In(SET_TYPES),
        vol.Optional("weight_kg", default=None): _OPT_FLOAT,
        vol.Optional("reps", default=None): _OPT_INT,
        vol.Optional("distance_meters", default=None): _OPT_INT,
        vol.Optional("duration_seconds", default=None): _OPT_INT,
        vol.Optional("custom_metric", default=None): _OPT_FLOAT,
        vol.Optional("rep_range"): REP_RANGE_SCHEMA,
    }
)

ROUTINE_EXERCISE_SCHEMA = vol.Schema(
    {
        vol.Required("exercise_template_id"): cv.string,
        vol.Optional("superset_id", default=None): _OPT_INT,
        vol.Optional("rest_seconds", default=None): _OPT_INT,
        vol.Optional("notes", default=None): vol.Any(None, cv.string),
        vol.Required("sets"): vol.All(cv.ensure_list, [ROUTINE_SET_SCHEMA]),
    }
)

BASE_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string})

PAGINATION = {
    vol.Optional("page", default=1): PAGE,
    vol.Optional("page_size", default=5): PAGE_SIZE,
}

WORKOUT_FIELDS = {
    vol.Required("title"): vol.All(cv.string, vol.Length(min=1)),
    vol.Optional("description", default=None): vol.Any(None, cv.string),
    vol.Required("start_time"): _utc_string,
    vol.Required("end_time"): _utc_string,
    vol.Optional("is_private", default=False): cv.boolean,
    vol.Required("exercises"): vol.All(cv.ensure_list, [WORKOUT_EXERCISE_SCHEMA]),
}

ROUTINE_FIELDS = {
    vol.Required("title"): vol.All(cv.string, vol.Length(min=1)),
    vol.Optional("notes"): vol.Any(None, cv.string),
    vol.Required("exercises"): vol.All(cv.ensure_list, [ROUTINE_EXERCISE_SCHEMA]),
}

MEASUREMENT_FIELDS = {
    vol.Optional(field): vol.Any(None, vol.Coerce(float))
    for field in BODY_MEASUREMENT_FIELDS
}

# ----------------------------------------------------------------- handlers


def _workout_payload(data: dict[str, Any]) -> JSON:
    return {
        key: data[key]
        for key in (
            "title",
            "description",
            "start_time",
            "end_time",
            "is_private",
            "exercises",
        )
    }


def _measurements(data: dict[str, Any]) -> JSON:
    return {key: data[key] for key in BODY_MEASUREMENT_FIELDS if key in data}


def _create_routine(client: HevyClient, data: dict[str, Any]) -> Awaitable[JSON]:
    return client.create_routine(
        {
            "title": data["title"],
            "folder_id": data.get("folder_id"),
            "notes": data.get("notes") or "",
            "exercises": data["exercises"],
        }
    )


def _update_routine(client: HevyClient, data: dict[str, Any]) -> Awaitable[JSON]:
    return client.update_routine(
        data["routine_id"],
        {
            "title": data["title"],
            "notes": data.get("notes"),
            "exercises": data["exercises"],
        },
    )


@dataclass(frozen=True)
class HevyService:
    """Definition of a service mapped to an API call."""

    schema: dict[Any, Any]
    call: Callable[[HevyClient, dict[str, Any]], Awaitable[Any]]
    write: bool = False


@dataclass(frozen=True)
class HevyCoordinatorService:
    """A service implemented on top of the coordinator (cache + client)."""

    schema: dict[Any, Any]
    call: Callable[[HevyCoordinator, dict[str, Any]], Awaitable[Any]]
    write: bool = False


# ------------------------------------------------------------ log_workout


def _has_measurement(value: dict[str, Any]) -> dict[str, Any]:
    if all(
        value.get(key) is None
        for key in ("weight_kg", "reps", "duration_seconds", "distance_meters")
    ):
        raise vol.Invalid(
            "each set needs weight_kg, reps, duration_seconds or distance_meters"
        )
    return value


LOG_EXERCISE_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Exclusive("name", "exercise"): cv.string,
            vol.Exclusive("exercise_template_id", "exercise"): cv.string,
            vol.Optional("superset_id", default=None): _OPT_INT,
            vol.Optional("notes", default=None): vol.Any(None, cv.string),
            vol.Required("sets"): vol.All(
                cv.ensure_list,
                vol.Length(min=1),
                [vol.All(WORKOUT_SET_SCHEMA, _has_measurement)],
            ),
        }
    ),
    cv.has_at_least_one_key("name", "exercise_template_id"),
)

LOG_WORKOUT_FIELDS = {
    vol.Required("title"): vol.All(cv.string, vol.Length(min=1)),
    vol.Required("exercises"): vol.All(
        cv.ensure_list, vol.Length(min=1), [LOG_EXERCISE_SCHEMA]
    ),
    vol.Optional("start_time"): _utc_string,
    vol.Optional("end_time"): _utc_string,
    vol.Optional("duration_minutes"): vol.All(
        vol.Coerce(float), vol.Range(min=1, max=1440)
    ),
    vol.Optional("description", default=None): vol.Any(None, cv.string),
    vol.Optional("is_private", default=False): cv.boolean,
}


def resolve_exercise(catalog: dict[str, JSON], name: str) -> str:
    """Map an exercise name to a template id (exact, then case-insensitive)."""
    titles = {t.get("title"): tid for tid, t in catalog.items() if t.get("title")}
    if name in titles:
        return titles[name]
    lowered = {title.casefold(): tid for title, tid in titles.items()}
    if name.casefold() in lowered:
        return lowered[name.casefold()]
    suggestions = difflib.get_close_matches(name, list(titles), n=5, cutoff=0.4)
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="unknown_exercise",
        translation_placeholders={
            "name": name,
            "suggestions": ", ".join(suggestions) or "-",
        },
    )


def _format_time(value: datetime) -> str:
    return dt_util.as_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def extract_workout(response: Any) -> JSON:
    """Return the workout object from a create/update response."""
    if isinstance(response, dict):
        inner = response.get("workout", response)
        if isinstance(inner, list):
            inner = inner[0] if inner else {}
        if isinstance(inner, dict):
            return inner
    if isinstance(response, list) and response and isinstance(response[0], dict):
        return response[0]
    return {}


async def _log_workout(coordinator: HevyCoordinator, data: dict[str, Any]) -> JSON:
    end = cv.datetime(data["end_time"]) if "end_time" in data else dt_util.utcnow()
    if "start_time" in data:
        start = cv.datetime(data["start_time"])
    elif "duration_minutes" in data:
        start = end - timedelta(minutes=data["duration_minutes"])
    else:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="start_or_duration"
        )
    if start >= end:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="start_after_end"
        )
    catalog: dict[str, JSON] = {}
    if any("name" in ex for ex in data["exercises"]):
        catalog = await coordinator.async_ensure_catalog()
    exercises = [
        {
            "exercise_template_id": ex.get("exercise_template_id")
            or resolve_exercise(catalog, ex["name"]),
            "superset_id": ex["superset_id"],
            "notes": ex["notes"],
            "sets": ex["sets"],
        }
        for ex in data["exercises"]
    ]
    response = await coordinator.client.create_workout(
        {
            "title": data["title"],
            "description": data["description"],
            "start_time": _format_time(start),
            "end_time": _format_time(end),
            "is_private": data["is_private"],
            "exercises": exercises,
        }
    )
    workout = extract_workout(response)
    return {"workout_id": workout.get("id"), "title": workout.get("title")}


# ------------------------------------------------------ cache-based reads


async def _get_workout_history(
    coordinator: HevyCoordinator, data: dict[str, Any]
) -> JSON:
    since = dt_util.utcnow() - timedelta(days=data["days"])
    templates = coordinator.data.templates
    workouts = [
        workout_summary(w, templates)
        for w in coordinator.data.workouts
        if (t := parse_time(w.get("start_time"))) is not None and t >= since
    ]
    durations = [w["duration_minutes"] for w in workouts if w["duration_minutes"]]
    total_volume = round(sum(w["volume_kg"] for w in workouts), 2)
    days = {
        dt_util.as_local(t).date()
        for w in workouts
        if (t := parse_time(w["start_time"])) is not None
    }
    return {
        "summary": {
            "days": data["days"],
            "total_workouts": len(workouts),
            "workout_days": len(days),
            "total_volume_kg": total_volume,
            "avg_duration_minutes": round(sum(durations) / len(durations), 1)
            if durations
            else None,
            "avg_volume_kg": round(total_volume / len(workouts), 2)
            if workouts
            else None,
        },
        "workouts": workouts,
    }


async def _get_exercise_catalog(
    coordinator: HevyCoordinator, data: dict[str, Any]
) -> JSON:
    catalog = await coordinator.async_ensure_catalog()
    exercises = sorted(
        (
            {
                "id": tid,
                "title": t.get("title"),
                "type": t.get("type"),
                "muscle_group": t.get("primary_muscle_group"),
                "is_custom": t.get("is_custom"),
            }
            for tid, t in catalog.items()
        ),
        key=lambda e: (e["title"] or "").casefold(),
    )
    return {"count": len(exercises), "exercises": exercises}


COORDINATOR_SERVICES: dict[str, HevyCoordinatorService] = {
    "log_workout": HevyCoordinatorService(LOG_WORKOUT_FIELDS, _log_workout, write=True),
    "get_workout_history": HevyCoordinatorService(
        {
            vol.Optional("days", default=30): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=3650)
            )
        },
        _get_workout_history,
    ),
    "get_exercise_catalog": HevyCoordinatorService({}, _get_exercise_catalog),
}


SERVICES: dict[str, HevyService] = {
    # User
    "get_user_info": HevyService({}, lambda c, d: c.get_user_info()),
    # Workouts
    "get_workouts": HevyService(
        PAGINATION, lambda c, d: c.get_workouts(d["page"], d["page_size"])
    ),
    "get_workout": HevyService(
        {vol.Required("workout_id"): cv.string},
        lambda c, d: c.get_workout(d["workout_id"]),
    ),
    "get_workout_count": HevyService({}, lambda c, d: c.get_workout_count()),
    "get_workout_events": HevyService(
        {vol.Optional("since", default="1970-01-01T00:00:00Z"): _utc_string}
        | PAGINATION,
        lambda c, d: c.get_workout_events(d["since"], d["page"], d["page_size"]),
    ),
    "create_workout": HevyService(
        WORKOUT_FIELDS,
        lambda c, d: c.create_workout(_workout_payload(d)),
        write=True,
    ),
    "update_workout": HevyService(
        {vol.Required("workout_id"): cv.string} | WORKOUT_FIELDS,
        lambda c, d: c.update_workout(d["workout_id"], _workout_payload(d)),
        write=True,
    ),
    # Routines
    "get_routines": HevyService(
        PAGINATION, lambda c, d: c.get_routines(d["page"], d["page_size"])
    ),
    "get_routine": HevyService(
        {vol.Required("routine_id"): cv.string},
        lambda c, d: c.get_routine(d["routine_id"]),
    ),
    "create_routine": HevyService(
        {vol.Optional("folder_id"): _OPT_INT} | ROUTINE_FIELDS,
        _create_routine,
        write=True,
    ),
    "update_routine": HevyService(
        {vol.Required("routine_id"): cv.string} | ROUTINE_FIELDS,
        _update_routine,
        write=True,
    ),
    # Routine folders
    "get_routine_folders": HevyService(
        PAGINATION, lambda c, d: c.get_routine_folders(d["page"], d["page_size"])
    ),
    "get_routine_folder": HevyService(
        {vol.Required("folder_id"): vol.Coerce(int)},
        lambda c, d: c.get_routine_folder(d["folder_id"]),
    ),
    "create_routine_folder": HevyService(
        {vol.Required("title"): vol.All(cv.string, vol.Length(min=1))},
        lambda c, d: c.create_routine_folder(d["title"]),
        write=True,
    ),
    # Exercise templates
    "get_exercise_templates": HevyService(
        {
            vol.Optional("page", default=1): PAGE,
            vol.Optional("page_size", default=50): TEMPLATE_PAGE_SIZE,
        },
        lambda c, d: c.get_exercise_templates(d["page"], d["page_size"]),
    ),
    "get_exercise_template": HevyService(
        {vol.Required("exercise_template_id"): cv.string},
        lambda c, d: c.get_exercise_template(d["exercise_template_id"]),
    ),
    "create_exercise_template": HevyService(
        {
            vol.Required("title"): vol.All(cv.string, vol.Length(min=1)),
            vol.Required("exercise_type"): vol.In(EXERCISE_TYPES),
            vol.Required("equipment_category"): vol.In(EQUIPMENT_CATEGORIES),
            vol.Required("muscle_group"): vol.In(MUSCLE_GROUPS),
            vol.Optional("other_muscles", default=list): vol.All(
                cv.ensure_list, [vol.In(MUSCLE_GROUPS)]
            ),
        },
        lambda c, d: c.create_exercise_template(
            {
                key: d[key]
                for key in (
                    "title",
                    "exercise_type",
                    "equipment_category",
                    "muscle_group",
                    "other_muscles",
                )
            }
        ),
        write=True,
    ),
    "get_exercise_history": HevyService(
        {
            vol.Required("exercise_template_id"): cv.string,
            vol.Optional("start_date"): _utc_string,
            vol.Optional("end_date"): _utc_string,
        },
        lambda c, d: c.get_exercise_history(
            d["exercise_template_id"], d.get("start_date"), d.get("end_date")
        ),
    ),
    # Body measurements
    "get_body_measurements": HevyService(
        {
            vol.Optional("page", default=1): PAGE,
            vol.Optional("page_size", default=10): PAGE_SIZE,
        },
        lambda c, d: c.get_body_measurements(d["page"], d["page_size"]),
    ),
    "get_body_measurement": HevyService(
        {vol.Required("date"): _date_string},
        lambda c, d: c.get_body_measurement(d["date"]),
    ),
    "create_body_measurement": HevyService(
        {vol.Required("date"): _date_string} | MEASUREMENT_FIELDS,
        lambda c, d: c.create_body_measurement({"date": d["date"]} | _measurements(d)),
        write=True,
    ),
    "update_body_measurement": HevyService(
        {vol.Required("date"): _date_string} | MEASUREMENT_FIELDS,
        lambda c, d: c.update_body_measurement(d["date"], _measurements(d)),
        write=True,
    ),
}


def _get_entry(hass: HomeAssistant, call: ServiceCall) -> HevyConfigEntry:
    """Resolve the config entry targeted by a service call."""
    entry_id: str | None = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_found",
                translation_placeholders={"entry_id": entry_id},
            )
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_loaded",
                translation_placeholders={"entry_id": entry_id},
            )
        return entry
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if len(entries) != 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_required" if entries else "no_entries",
        )
    return entries[0]


def _make_handler(
    hass: HomeAssistant, service: HevyService | HevyCoordinatorService
) -> Callable[[ServiceCall], Awaitable[ServiceResponse]]:
    async def _handle(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call)
        coordinator = entry.runtime_data
        data = {k: v for k, v in call.data.items() if k != ATTR_CONFIG_ENTRY_ID}
        try:
            if isinstance(service, HevyCoordinatorService):
                result = await service.call(coordinator, data)
            else:
                result = await service.call(coordinator.client, data)
        except HevyAuthError as err:
            entry.async_start_reauth(hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except HevyNotFoundError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="not_found",
                translation_placeholders={"error": str(err)},
            ) from err
        except HevyRateLimitError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="rate_limited"
            ) from err
        except HevyApiError as err:
            exc = (
                ServiceValidationError
                if 400 <= err.status < 500
                else HomeAssistantError
            )
            raise exc(
                translation_domain=DOMAIN,
                translation_key="api_error",
                translation_placeholders={"error": str(err)},
            ) from err
        except HevyError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="api_error",
                translation_placeholders={"error": str(err)},
            ) from err

        if service.write:
            await coordinator.async_request_refresh()

        if not call.return_response:
            return None
        if isinstance(result, dict):
            return result
        return {"data": result}

    return _handle


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register all Hevy services."""
    all_services: dict[str, HevyService | HevyCoordinatorService] = {
        **SERVICES,
        **COORDINATOR_SERVICES,
    }
    for name, service in all_services.items():
        hass.services.async_register(
            DOMAIN,
            name,
            _make_handler(hass, service),
            schema=BASE_SCHEMA.extend(service.schema),
            supports_response=(
                SupportsResponse.OPTIONAL if service.write else SupportsResponse.ONLY
            ),
        )
