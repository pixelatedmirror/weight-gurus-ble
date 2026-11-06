"""Config flow for Weight Gurus BLE integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util.unit_system import METRIC_SYSTEM

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

GENDER_OPTIONS = {
    GENDER_MALE: "Male",
    GENDER_FEMALE: "Female",
    GENDER_UNSPECIFIED: "Not specified",
}

UNIT_OPTIONS = {
    UNIT_IN: "Inches (in)",
    UNIT_CM: "Centimeters (cm)",
}


def _is_metric(hass: HomeAssistant) -> bool:
    """Determine whether Home Assistant is configured for metric units."""
    units = getattr(hass.config, "units", None)
    if units is None:
        return False
    return (
        getattr(units, "is_metric", False)
        or units is METRIC_SYSTEM
        or getattr(units, "name", "") == "metric"
    )


class WeightGurusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Weight Gurus BLE."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_address: str | None = None
        self._discovered_device_name: str | None = None

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
        """Handle incoming bluetooth auto-discovery."""
        _LOGGER.debug(
            "Auto-discovered Weight Gurus BLE device: address=%s, name=%s, rssi=%s",
            discovery_info.address,
            discovery_info.name,
            discovery_info.rssi,
        )

        await self.async_set_unique_id(discovery_info.address.lower())
        self._abort_if_unique_id_configured()

        self._discovered_address = discovery_info.address.upper()
        self._discovered_device_name = discovery_info.name or DEFAULT_NAME

        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual or discovery setup on a single unified screen."""
        errors: dict[str, str] = {}
        is_metric = _is_metric(self.hass)

        if user_input is not None:
            selected_addr = user_input.get(CONF_ADDRESS, "").strip()
            manual_addr = user_input.get("manual_mac", "").strip()
            if manual_addr:
                raw_address = manual_addr
            elif selected_addr and selected_addr != "manual":
                raw_address = selected_addr
            else:
                raw_address = self._discovered_address or ""

            clean_mac = raw_address.replace("-", ":").upper()

            parts = clean_mac.split(":")
            if len(parts) != 6 or not all(len(p) == 2 and all(c in "0123456789ABCDEF" for c in p) for p in parts):
                errors["base"] = "invalid_mac"
            else:
                await self.async_set_unique_id(clean_mac.lower())
                self._abort_if_unique_id_configured()

                unit = user_input.get(CONF_HEIGHT_UNIT, UNIT_CM if is_metric else UNIT_IN)
                height_val = float(user_input.get(CONF_HEIGHT, DEFAULT_HEIGHT_CM if unit == UNIT_CM else DEFAULT_HEIGHT_IN))
                height_cm = height_val if unit == UNIT_CM else round(height_val * 2.54, 1)

                data = {
                    CONF_MAC: clean_mac,
                    CONF_NAME: user_input.get(CONF_NAME, self._discovered_device_name or DEFAULT_NAME),
                    CONF_HEIGHT: height_val,
                    CONF_HEIGHT_UNIT: unit,
                    "height_cm": height_cm,
                    CONF_AGE: int(user_input.get(CONF_AGE, DEFAULT_AGE)),
                    CONF_GENDER: user_input.get(CONF_GENDER, DEFAULT_GENDER),
                }

                return self.async_create_entry(
                    title=data[CONF_NAME],
                    data=data,
                )

        # Discover devices and filter for scale candidates
        scale_candidates: dict[str, str] = {}
        for service_info in async_discovered_service_info(self.hass, connectable=False):
            addr = service_info.address.upper()
            name = service_info.name or ""
            name_lower = name.lower()
            service_uuids = [str(u).lower() for u in (service_info.service_uuids or [])]

            if (
                any(p in name_lower for p in ("ls212", "lifesense", "0383", "0376", "gbf", "weight", "transtek", "greater", "goods", "scale"))
                or addr.startswith("A4:C1:38")
                or any("20568521" in u or "0d005750" in u or "000078b2" in u or "0000181d" in u or "0000181b" in u for u in service_uuids)
            ):
                display_name = name or "Weight Gurus Scale"
                scale_candidates[addr] = f"{display_name} ({addr})"

        if self._discovered_address and self._discovered_address not in scale_candidates:
            scale_candidates[self._discovered_address] = (
                f"{self._discovered_device_name or 'Weight Gurus Scale'} ({self._discovered_address})"
            )

        unit = UNIT_CM if is_metric else UNIT_IN
        default_height = DEFAULT_HEIGHT_CM if unit == UNIT_CM else DEFAULT_HEIGHT_IN
        min_h = 50.0 if unit == UNIT_CM else 20.0
        max_h = 250.0 if unit == UNIT_CM else 100.0
        step_h = 1.0 if unit == UNIT_CM else 0.5

        schema_dict: dict[Any, Any] = {}

        if scale_candidates:
            options = [
                {"value": k, "label": v}
                for k, v in scale_candidates.items()
            ]
            options.append({"value": "manual", "label": "Enter MAC address manually below"})
            default_addr = (
                self._discovered_address
                if (self._discovered_address and self._discovered_address in scale_candidates)
                else next(iter(scale_candidates))
            )
            schema_dict[vol.Required(CONF_ADDRESS, default=default_addr)] = SelectSelector(
                SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
            )
            schema_dict[vol.Optional("manual_mac", default="")] = str
        else:
            schema_dict[vol.Required(CONF_ADDRESS, default="A4:C1:38:36:65:D3")] = str

        schema_dict[vol.Required(CONF_NAME, default=self._discovered_device_name or DEFAULT_NAME)] = str
        schema_dict[vol.Required(CONF_HEIGHT, default=default_height)] = NumberSelector(
            NumberSelectorConfig(min=min_h, max=max_h, step=step_h, mode=NumberSelectorMode.BOX)
        )
        schema_dict[vol.Required(CONF_HEIGHT_UNIT, default=unit)] = vol.In(UNIT_OPTIONS)
        schema_dict[vol.Required(CONF_AGE, default=DEFAULT_AGE)] = NumberSelector(
            NumberSelectorConfig(min=5, max=120, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="years")
        )
        schema_dict[vol.Required(CONF_GENDER, default=DEFAULT_GENDER)] = vol.In(GENDER_OPTIONS)

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
        is_metric = _is_metric(self.hass)

        if user_input is not None:
            unit = user_input.get(CONF_HEIGHT_UNIT, UNIT_CM if is_metric else UNIT_IN)
            height_val = float(user_input.get(CONF_HEIGHT, DEFAULT_HEIGHT_CM if unit == UNIT_CM else DEFAULT_HEIGHT_IN))
            height_cm = height_val if unit == UNIT_CM else round(height_val * 2.54, 1)

            options = {
                CONF_NAME: user_input.get(CONF_NAME, self.config_entry.data.get(CONF_NAME, DEFAULT_NAME)),
                CONF_HEIGHT: height_val,
                CONF_HEIGHT_UNIT: unit,
                "height_cm": height_cm,
                CONF_AGE: int(user_input.get(CONF_AGE, DEFAULT_AGE)),
                CONF_GENDER: user_input.get(CONF_GENDER, DEFAULT_GENDER),
            }
            return self.async_create_entry(title="", data=options)

        current_data = {**self.config_entry.data, **self.config_entry.options}
        unit = current_data.get(CONF_HEIGHT_UNIT, UNIT_CM if is_metric else UNIT_IN)
        default_height = float(current_data.get(CONF_HEIGHT, DEFAULT_HEIGHT_CM if unit == UNIT_CM else DEFAULT_HEIGHT_IN))
        min_h = 50.0 if unit == UNIT_CM else 20.0
        max_h = 250.0 if unit == UNIT_CM else 100.0
        step_h = 1.0 if unit == UNIT_CM else 0.5

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=current_data.get(CONF_NAME, DEFAULT_NAME)): str,
                vol.Required(CONF_HEIGHT, default=default_height): NumberSelector(
                    NumberSelectorConfig(min=min_h, max=max_h, step=step_h, mode=NumberSelectorMode.BOX)
                ),
                vol.Required(CONF_HEIGHT_UNIT, default=unit): vol.In(UNIT_OPTIONS),
                vol.Required(CONF_AGE, default=int(current_data.get(CONF_AGE, DEFAULT_AGE))): NumberSelector(
                    NumberSelectorConfig(min=5, max=120, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="years")
                ),
                vol.Required(CONF_GENDER, default=current_data.get(CONF_GENDER, DEFAULT_GENDER)): vol.In(GENDER_OPTIONS),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )
