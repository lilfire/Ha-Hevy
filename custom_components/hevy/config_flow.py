"""Config flow for Hevy."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import JSON, HevyAuthError, HevyClient, HevyError
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

API_KEY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    }
)


class HevyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hevy."""

    VERSION = 1

    async def _validate(self, api_key: str) -> tuple[JSON | None, dict[str, str]]:
        """Validate the API key, returning user info or errors."""
        client = HevyClient(async_get_clientsession(self.hass), api_key)
        try:
            info = await client.get_user_info()
        except HevyAuthError:
            return None, {"base": "invalid_auth"}
        except HevyError:
            return None, {"base": "cannot_connect"}
        except Exception:
            _LOGGER.exception("Unexpected error validating Hevy API key")
            return None, {"base": "unknown"}
        user = info.get("data") or {}
        if not user.get("id"):
            return None, {"base": "unknown"}
        return user, {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            user, errors = await self._validate(api_key)
            if user is not None:
                await self.async_set_unique_id(str(user["id"]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user.get("name") or "Hevy",
                    data={CONF_API_KEY: api_key},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=API_KEY_SCHEMA,
            errors=errors,
            description_placeholders={"url": "https://hevy.com/settings?developer"},
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauth when the API key is rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            user, errors = await self._validate(api_key)
            if user is not None:
                await self.async_set_unique_id(str(user["id"]))
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={CONF_API_KEY: api_key},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=API_KEY_SCHEMA,
            errors=errors,
            description_placeholders={"url": "https://hevy.com/settings?developer"},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> HevyOptionsFlow:
        """Return the options flow."""
        return HevyOptionsFlow()


class HevyOptionsFlow(OptionsFlow):
    """Hevy options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )
        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, int(DEFAULT_SCAN_INTERVAL.total_seconds() // 60)
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL_MINUTES,
                            max=MAX_SCAN_INTERVAL_MINUTES,
                            step=1,
                            unit_of_measurement="min",
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )
