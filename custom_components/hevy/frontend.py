"""Serve and auto-load the Hevy live workout card."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

CARD_FILENAME = "hevy-workout-card.js"
CARD_URL = f"/{DOMAIN}_static/{CARD_FILENAME}"
DATA_FRONTEND_REGISTERED = f"{DOMAIN}_frontend_registered"


async def async_register_card(hass: HomeAssistant) -> None:
    """Expose the card JS and add it to the frontend's extra modules."""
    if hass.data.get(DATA_FRONTEND_REGISTERED) or hass.http is None:
        return
    hass.data[DATA_FRONTEND_REGISTERED] = True
    path = Path(__file__).parent / "www" / CARD_FILENAME
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(path), cache_headers=False)]
    )
    if "frontend" in hass.config.components:
        # Imported lazily: the frontend is an after-dependency, not required.
        from homeassistant.components.frontend import add_extra_js_url  # noqa: PLC0415

        manifest = await hass.async_add_executor_job(
            (Path(__file__).parent / "manifest.json").read_text
        )
        version = json.loads(manifest).get("version", "0")
        add_extra_js_url(hass, f"{CARD_URL}?v={version}")
