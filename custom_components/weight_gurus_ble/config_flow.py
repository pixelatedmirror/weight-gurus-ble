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
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    CONF_AGE,
    CONF_GENDER,
    CONF_HEIGHT,
    CONF_HEIGHT_UNIT,
    CONF_MAC,
    CONF_NAME,
    DEFAULT_AGE,
    DEFAULT_GENDER,
    DEFAULT_HEIGHT_CM,
    DEFAULT_HEIGHT_IN,
    DEFAULT_NAME,
    DOMAIN,
    GENDER_FEMALE,
    GENDER_MALE,
    GENDER_UNSPECIFIED,
    UNIT_CM,
    UNIT_IN,
)

_LOGGER = logging.getLogger(__name__)


def _build_user_profile_schema(
    is_metric: bool,
    default_name: str,
    current_height: float | None = None,
    current_unit: str | None = None,
    current_age: int | None = None,
    current_gender: str | None = None,
) -> vol.Schema:
    """Build a user profile schema using NumberSelectorMode.BOX."""
    unit = current_unit or (UNIT_CM if is_metric else UNIT_IN)
    default_height = current_height or (DEFAULT_HEIGHT_CM if unit == UNIT_CM else DEFAULT_HEIGHT_IN)
    default_age = current_age or DEFAULT_AGE
    default_gender = current_gender or DEFAULT_GENDER

    min_h = 50.0 if unit == UNIT_CM else 20.0
    max_h = 250.0 if unit == UNIT_CM else 100.0
    step_h = 1.0 if unit == UNIT_CM else 0.5

    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=default_name): TextSelector(),
            vol.Required(CONF_HEIGHT, default=default_height): NumberSelector(
                NumberSelectorConfig(
                    min=min_h,
                    max=max_h,
                    step=step_h,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(CONF_HEIGHT_UNIT, default=unit): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=UNIT_IN, label="Inches (in)"),
                        SelectOptionDict(value=UNIT_CM, label="Centimeters (cm)"),
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="height_unit",
                )
            ),
            vol.Required(CONF_AGE, default=default_age): NumberSelector(
                NumberSelectorConfig(
                    min=5,
                    max=120,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="years",
                )
            ),
            vol.Required(CONF_GENDER, default=default_gender): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=GENDER_MALE, label="Male"),
                        SelectOptionDict(value=GENDER_FEMALE, label="Female"),
                        SelectOptionDict(value=GENDER_UNSPECIFIED, label="Not specified"),
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="gender",
                )
            ),
        }
    )


class WeightGurusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Weight Gurus BLE."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_device_name: str | None = None
        self._discovered_address: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return WeightGurusOptionsFlowHandler(config_entry)

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
        """Confirm discovery and configure user profile metrics."""
        is_metric = self.hass.config.units.is_metric

        if user_input is not None:
            height_val = float(user_input.get(CONF_HEIGHT, DEFAULT_HEIGHT_CM if is_metric else DEFAULT_HEIGHT_IN))
            height_unit = user_input.get(CONF_HEIGHT_UNIT, UNIT_CM if is_metric else UNIT_IN)
            height_cm = height_val if height_unit == UNIT_CM else round(height_val * 2.54, 1)

            data = {
                CONF_MAC: self._discovered_address,
                CONF_NAME: user_input.get(CONF_NAME, self._discovered_device_name),
                CONF_HEIGHT: height_val,
                CONF_HEIGHT_UNIT: height_unit,
                "height_cm": height_cm,
                CONF_AGE: int(user_input.get(CONF_AGE, DEFAULT_AGE)),
                CONF_GENDER: user_input.get(CONF_GENDER, DEFAULT_GENDER),
            }
            return self.async_create_entry(
                title=data[CONF_NAME],
                data=data,
            )

        schema = _build_user_profile_schema(
            is_metric=is_metric,
            default_name=self._discovered_device_name or DEFAULT_NAME,
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


class WeightGurusOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Weight Gurus BLE to reconfigure profile at any time."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        is_metric = self.hass.config.units.is_metric

        if user_input is not None:
            height_val = float(user_input.get(CONF_HEIGHT, DEFAULT_HEIGHT_CM if is_metric else DEFAULT_HEIGHT_IN))
            height_unit = user_input.get(CONF_HEIGHT_UNIT, UNIT_CM if is_metric else UNIT_IN)
            height_cm = height_val if height_unit == UNIT_CM else round(height_val * 2.54, 1)

            options = {
                CONF_NAME: user_input.get(CONF_NAME, self.config_entry.data.get(CONF_NAME, DEFAULT_NAME)),
                CONF_HEIGHT: height_val,
                CONF_HEIGHT_UNIT: height_unit,
                "height_cm": height_cm,
                CONF_AGE: int(user_input.get(CONF_AGE, DEFAULT_AGE)),
                CONF_GENDER: user_input.get(CONF_GENDER, DEFAULT_GENDER),
            }
            return self.async_create_entry(title="", data=options)

        current_data = {**self.config_entry.data, **self.config_entry.options}

        schema = _build_user_profile_schema(
            is_metric=is_metric,
            default_name=current_data.get(CONF_NAME, DEFAULT_NAME),
            current_height=current_data.get(CONF_HEIGHT),
            current_unit=current_data.get(CONF_HEIGHT_UNIT),
            current_age=current_data.get(CONF_AGE),
            current_gender=current_data.get(CONF_GENDER),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )
