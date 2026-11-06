"""Sensor platform for Weight Gurus BLE."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfMass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MAC, CONF_NAME, DOMAIN
from .coordinator import WeightGurusCoordinator

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="weight",
        name="Weight",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:scale-bathroom",
    ),
    SensorEntityDescription(
        key="body_fat",
        name="Body Fat",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:percent",
    ),
    SensorEntityDescription(
        key="water_percentage",
        name="Body Water",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
    ),
    SensorEntityDescription(
        key="muscle_percentage",
        name="Muscle Mass",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:arm-flex",
    ),
    SensorEntityDescription(
        key="bmi",
        name="BMI",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calculator-variant",
    ),
    SensorEntityDescription(
        key="last_measurement",
        name="Last Measurement",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-check-outline",
    ),
    SensorEntityDescription(
        key="rssi",
        name="Signal Strength",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        icon="mdi:bluetooth",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Weight Gurus sensor entities from a config entry."""
    coordinator: WeightGurusCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        WeightGurusSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class WeightGurusSensor(SensorEntity):
    """Representation of a Weight Gurus sensor entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WeightGurusCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        self.coordinator = coordinator
        self.entry = entry
        self.entity_description = description

        self._attr_unique_id = f"{coordinator.mac}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.mac)},
            name=entry.data.get(CONF_NAME, f"Weight Gurus {coordinator.mac[-5:]}"),
            manufacturer="Greater Goods / Weight Gurus",
            model="0383 Smart Scale",
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return True

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        key = self.entity_description.key
        if key == "weight":
            return self.coordinator.weight_kg
        if key == "body_fat":
            return self.coordinator.body_fat
        if key == "water_percentage":
            return self.coordinator.water_percentage
        if key == "muscle_percentage":
            return self.coordinator.muscle_percentage
        if key == "bmi":
            return self.coordinator.bmi
        if key == "last_measurement":
            return self.coordinator.last_measurement
        if key == "rssi":
            return self.coordinator.last_rssi
        return None

    async def async_added_to_hass(self) -> None:
        """Register listener when added to Home Assistant."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
