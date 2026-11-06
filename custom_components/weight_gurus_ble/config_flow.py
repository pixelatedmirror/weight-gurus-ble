"""Config flow for Weight Gurus BLE integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_AGE,
    CONF_GENDER,
    CONF_HEIGHT,
    CONF_MAC,
    CONF_NAME,
    DEFAULT_AGE,
    DEFAULT_GENDER,
    DEFAULT_HEIGHT_CM,
    DEFAULT_NAME,
    DOMAIN,
    GENDER_FEMALE,
    GENDER_MALE,
    GENDER_UNSPECIFIED,
)

_LOGGER = logging.getLogger(__name__)


class WeightGurusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Weight Gurus BLE."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_device_name: str | None = None
        self._discovered_address: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.debug(
            "Discovered Weight Gurus BLE device: address=%s, name=%s, rssi=%s",
            discovery_info.address,
            discovery_info.name,
            discovery_info.rssi,
        )

        await self.async_set_unique_id(discovery_info.address.lower())
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self._discovered_address = discovery_info.address
        self._discovered_device_name = discovery_info.name or DEFAULT_NAME

        self.context["title_placeholders"] = {
            "name": self._discovered_device_name,
            "address": self._discovered_address,
        }

        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery and configure optional user profile metrics."""
        if user_input is not None:
            data = {
                CONF_MAC: self._discovered_address,
                CONF_NAME: user_input.get(CONF_NAME, self._discovered_device_name),
                CONF_HEIGHT: user_input.get(CONF_HEIGHT, DEFAULT_HEIGHT_CM),
                CONF_AGE: user_input.get(CONF_AGE, DEFAULT_AGE),
                CONF_GENDER: user_input.get(CONF_GENDER, DEFAULT_GENDER),
            }
            return self.async_create_entry(
                title=data[CONF_NAME],
                data=data,
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=self._discovered_device_name or DEFAULT_NAME): str,
                vol.Optional(CONF_HEIGHT, default=DEFAULT_HEIGHT_CM): vol.All(
                    vol.Coerce(int), vol.Range(min=50, max=250)
                ),
                vol.Optional(CONF_AGE, default=DEFAULT_AGE): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=120)
                ),
                vol.Optional(CONF_GENDER, default=DEFAULT_GENDER): vol.In(
                    [GENDER_MALE, GENDER_FEMALE, GENDER_UNSPECIFIED]
                ),
            }
        )

        return self.async_show_form(
            step_id="confirm",
            data_schema=schema,
            description_placeholders={
                "name": self._discovered_device_name or DEFAULT_NAME,
                "address": self._discovered_address or "Unknown",
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual setup by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip()
            await self.async_set_unique_id(address.lower())
            self._abort_if_unique_id_configured()

            self._discovered_address = address
            self._discovered_device_name = user_input.get(CONF_NAME, DEFAULT_NAME)
            return await self.async_step_confirm()

        # Discover nearby connectable devices to offer a selection list
        discovered_devices: dict[str, str] = {}
        for service_info in async_discovered_service_info(self.hass, connectable=True):
            addr = service_info.address
            name = service_info.name or "Unknown device"
            discovered_devices[addr] = f"{name} ({addr})"

        schema_dict: dict[Any, Any] = {}
        if discovered_devices:
            schema_dict[vol.Required(CONF_ADDRESS)] = vol.In(discovered_devices)
        else:
            schema_dict[vol.Required(CONF_ADDRESS)] = str

        schema_dict[vol.Optional(CONF_NAME, default=DEFAULT_NAME)] = str

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )
