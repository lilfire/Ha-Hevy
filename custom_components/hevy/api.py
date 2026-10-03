"""Async client for the Hevy public API (https://api.hevyapp.com/docs/).

Covers every endpoint of API v1. Requires a Hevy Pro API key, sent in the
``api-key`` header.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
from typing import Any

import aiohttp

from .const import API_BASE_URL

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

type JSON = dict[str, Any]


class HevyError(Exception):
    """Base error for the Hevy API."""


class HevyConnectionError(HevyError):
    """Error communicating with Hevy."""


class HevyAuthError(HevyError):
    """The API key was rejected."""


class HevyNotFoundError(HevyError):
    """The requested resource does not exist."""


class HevyRateLimitError(HevyError):
    """Hevy rate-limited the request."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        """Initialize the error."""
        super().__init__(message)
        self.retry_after = retry_after


class HevyApiError(HevyError):
    """Hevy returned an unexpected error response."""

    def __init__(self, message: str, status: int) -> None:
        """Initialize the error."""
        super().__init__(message)
        self.status = status


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    """Drop ``None`` values from query parameters."""
    return {key: value for key, value in params.items() if value is not None}


class HevyClient:
    """Thin async wrapper around the Hevy REST API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        base_url: str = API_BASE_URL,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        """Perform a request and return the decoded JSON body (or ``{}``)."""
        url = f"{self._base_url}{path}"
        headers = {"api-key": self._api_key, "accept": "application/json"}
        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                params=_clean(params) if params else None,
                json=json,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                text = await resp.text()
                status = resp.status
                retry_after = resp.headers.get("Retry-After")
                data: Any = None
                if text:
                    try:
                        data = await resp.json(content_type=None)
                    except ValueError:
                        data = text
        except TimeoutError as err:
            raise HevyConnectionError(f"Timeout calling {method} {path}") from err
        except aiohttp.ClientError as err:
            raise HevyConnectionError(f"Error calling {method} {path}: {err}") from err

        if status < 400:
            return data if data is not None else {}

        message = data.get("error") if isinstance(data, dict) else data
        message = str(message or f"HTTP {status}")
        _LOGGER.debug("Hevy %s %s failed (%s): %s", method, path, status, message)
        if status in (401, 403):
            raise HevyAuthError(message)
        if status == 404:
            raise HevyNotFoundError(message)
        if status == 429:
            seconds: float | None = None
            if retry_after:
                try:
                    seconds = float(retry_after)
                except ValueError:
                    seconds = None
            raise HevyRateLimitError(message, seconds)
        raise HevyApiError(message, status)

    # ------------------------------------------------------------------ user

    async def get_user_info(self) -> JSON:
        """GET /v1/user/info."""
        return await self._request("GET", "/v1/user/info")

    # -------------------------------------------------------------- workouts

    async def get_workouts(self, page: int = 1, page_size: int = 5) -> JSON:
        """GET /v1/workouts (paginated, max 10 per page)."""
        return await self._request(
            "GET", "/v1/workouts", params={"page": page, "pageSize": page_size}
        )

    async def get_workout_count(self) -> JSON:
        """GET /v1/workouts/count."""
        return await self._request("GET", "/v1/workouts/count")

    async def get_workout_events(
        self, since: str | None = None, page: int = 1, page_size: int = 5
    ) -> JSON:
        """GET /v1/workouts/events (updated/deleted workouts since a date)."""
        return await self._request(
            "GET",
            "/v1/workouts/events",
            params={"since": since, "page": page, "pageSize": page_size},
        )

    async def get_workout(self, workout_id: str) -> JSON:
        """GET /v1/workouts/{workoutId}."""
        return await self._request("GET", f"/v1/workouts/{workout_id}")

    async def create_workout(self, workout: JSON) -> JSON:
        """POST /v1/workouts."""
        return await self._request("POST", "/v1/workouts", json={"workout": workout})

    async def update_workout(self, workout_id: str, workout: JSON) -> JSON:
        """PUT /v1/workouts/{workoutId}."""
        return await self._request(
            "PUT", f"/v1/workouts/{workout_id}", json={"workout": workout}
        )

    # -------------------------------------------------------------- routines

    async def get_routines(self, page: int = 1, page_size: int = 5) -> JSON:
        """GET /v1/routines (paginated, max 10 per page)."""
        return await self._request(
            "GET", "/v1/routines", params={"page": page, "pageSize": page_size}
        )

    async def get_routine(self, routine_id: str) -> JSON:
        """GET /v1/routines/{routineId}."""
        return await self._request("GET", f"/v1/routines/{routine_id}")

    async def create_routine(self, routine: JSON) -> JSON:
        """POST /v1/routines."""
        return await self._request("POST", "/v1/routines", json={"routine": routine})

    async def update_routine(self, routine_id: str, routine: JSON) -> JSON:
        """PUT /v1/routines/{routineId}."""
        return await self._request(
            "PUT", f"/v1/routines/{routine_id}", json={"routine": routine}
        )

    # ------------------------------------------------------- routine folders

    async def get_routine_folders(self, page: int = 1, page_size: int = 5) -> JSON:
        """GET /v1/routine_folders (paginated, max 10 per page)."""
        return await self._request(
            "GET", "/v1/routine_folders", params={"page": page, "pageSize": page_size}
        )

    async def get_routine_folder(self, folder_id: int) -> JSON:
        """GET /v1/routine_folders/{folderId}."""
        return await self._request("GET", f"/v1/routine_folders/{folder_id}")

    async def create_routine_folder(self, title: str) -> JSON:
        """POST /v1/routine_folders."""
        return await self._request(
            "POST", "/v1/routine_folders", json={"routine_folder": {"title": title}}
        )

    # ----------------------------------------------------- exercise templates

    async def get_exercise_templates(self, page: int = 1, page_size: int = 5) -> JSON:
        """GET /v1/exercise_templates (paginated, max 100 per page)."""
        return await self._request(
            "GET",
            "/v1/exercise_templates",
            params={"page": page, "pageSize": page_size},
        )

    async def get_exercise_template(self, exercise_template_id: str) -> JSON:
        """GET /v1/exercise_templates/{exerciseTemplateId}."""
        return await self._request(
            "GET", f"/v1/exercise_templates/{exercise_template_id}"
        )

    async def create_exercise_template(self, exercise: JSON) -> JSON:
        """POST /v1/exercise_templates (create a custom exercise)."""
        return await self._request(
            "POST", "/v1/exercise_templates", json={"exercise": exercise}
        )

    async def get_exercise_history(
        self,
        exercise_template_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> JSON:
        """GET /v1/exercise_history/{exerciseTemplateId}."""
        return await self._request(
            "GET",
            f"/v1/exercise_history/{exercise_template_id}",
            params={"start_date": start_date, "end_date": end_date},
        )

    # ------------------------------------------------------ body measurements

    async def get_body_measurements(self, page: int = 1, page_size: int = 10) -> JSON:
        """GET /v1/body_measurements (paginated, max 10 per page)."""
        return await self._request(
            "GET",
            "/v1/body_measurements",
            params={"page": page, "pageSize": page_size},
        )

    async def get_body_measurement(self, date: str) -> JSON:
        """GET /v1/body_measurements/{date} (date as YYYY-MM-DD)."""
        return await self._request("GET", f"/v1/body_measurements/{date}")

    async def create_body_measurement(self, measurement: JSON) -> JSON:
        """POST /v1/body_measurements (409 if the date already exists)."""
        return await self._request("POST", "/v1/body_measurements", json=measurement)

    async def update_body_measurement(self, date: str, measurement: JSON) -> JSON:
        """PUT /v1/body_measurements/{date}; omitted fields are set to null."""
        return await self._request(
            "PUT", f"/v1/body_measurements/{date}", json=measurement
        )

    # --------------------------------------------------------------- helpers

    async def paginate(
        self,
        fetch: Callable[[int, int], Awaitable[JSON]],
        key: str,
        page_size: int,
        max_pages: int,
        stop: Callable[[list[JSON]], bool] | None = None,
    ) -> list[JSON]:
        """Collect ``key`` items across pages.

        Stops at ``page_count``, an empty page, a 404 past the first page
        (Hevy's end-of-list signal), ``max_pages`` or when ``stop`` returns
        True for the page just fetched.
        """
        items: list[JSON] = []
        page = 1
        while page <= max_pages:
            try:
                data = await fetch(page, page_size)
            except HevyNotFoundError:
                if page == 1:
                    raise
                break
            page_items = data.get(key) or []
            items.extend(page_items)
            page_count = data.get("page_count")
            if (
                not page_items
                or (isinstance(page_count, int) and page >= page_count)
                or (stop is not None and stop(page_items))
            ):
                break
            page += 1
            await asyncio.sleep(0)
        return items
