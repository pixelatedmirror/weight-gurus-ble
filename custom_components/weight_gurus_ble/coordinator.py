"""Data coordinator and Bluetooth connection manager for Weight Gurus BLE."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
import logging
import struct
import time
from typing import Any

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback

from .const import (
    ALL_BODY_CHARACTERISTICS,
    ALL_COMMAND_CHARACTERISTICS,
    ALL_WEIGHT_CHARACTERISTICS,
    CONF_HEIGHT,
    CONF_MAC,
    CONF_NAME,
    DEFAULT_HEIGHT_CM,
    DOMAIN,
    UUID_STANDARD_WEIGHT_MEASUREMENT,
    UUID_TRANSTEK_BODY,
    UUID_TRANSTEK_COMMAND,
    UUID_TRANSTEK_WEIGHT,
    UUID_WG_BODY,
    UUID_WG_COMMAND,
    UUID_WG_WEIGHT,
)

_LOGGER = logging.getLogger(__name__)


class WeightGurusCoordinator:
    """Manages active BLE connections and measurement callbacks for the scale."""

    def __init__(self, hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry_data = entry_data
        self.mac: str = entry_data[CONF_MAC].upper()
        self.name: str = entry_data.get(CONF_NAME, "Weight Gurus Scale")
        self.height_cm: int = entry_data.get(CONF_HEIGHT, DEFAULT_HEIGHT_CM)

        self._unsubscribe_bluetooth: CALLBACK_TYPE | None = None
        self._listeners: list[Callable[[], None]] = []
        self._connection_lock = asyncio.Lock()

        # Measurement state
        self.weight_kg: float | None = None
        self.weight_lbs: float | None = None
        self.body_fat: float | None = None
        self.water_percentage: float | None = None
        self.muscle_percentage: float | None = None
        self.bone_mass: float | None = None
        self.bmi: float | None = None
        self.calories: int | None = None
        self.last_measurement: datetime | None = None
        self.last_rssi: int | None = None

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> CALLBACK_TYPE:
        """Register a callback for sensor entity updates."""
        self._listeners.append(update_callback)

        @callback
        def remove_listener() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return remove_listener

    @callback
    def _async_notify_listeners(self) -> None:
        """Notify all listeners that new scale measurements are available."""
        for update_callback in self._listeners:
            update_callback()

    async def async_start(self) -> None:
        """Start listening for Bluetooth advertisements from the scale."""
        _LOGGER.info(
            "Starting Weight Gurus BLE listener for scale %s (%s)",
            self.name,
            self.mac,
        )

        self._unsubscribe_bluetooth = bluetooth.async_register_callback(
            self.hass,
            self._async_on_bluetooth_event,
            BluetoothCallbackMatcher(address=self.mac, connectable=True),
            BluetoothScanningMode.ACTIVE,
        )

    async def async_stop(self) -> None:
        """Stop listening for Bluetooth advertisements."""
        if self._unsubscribe_bluetooth:
            self._unsubscribe_bluetooth()
            self._unsubscribe_bluetooth = None
        _LOGGER.info("Stopped Weight Gurus BLE listener for %s", self.mac)

    @callback
    def _async_on_bluetooth_event(
        self,
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        """Handle incoming Bluetooth advertisements when the scale is stepped on."""
        self.last_rssi = service_info.rssi
        _LOGGER.debug(
            "Scale advertised: address=%s, rssi=%d, source=%s. Initiating connection.",
            service_info.address,
            service_info.rssi,
            service_info.source,
        )

        # Trigger background connection task
        self.hass.async_create_task(
            self._async_connect_and_sync(service_info),
            f"weight_gurus_sync_{self.mac}",
        )

    async def _async_connect_and_sync(
        self, service_info: BluetoothServiceInfoBleak
    ) -> None:
        """Establish active BLE GATT connection to read scale measurements."""
        if self._connection_lock.locked():
            _LOGGER.debug("Connection to %s is already in progress, skipping", self.mac)
            return

        async with self._connection_lock:
            _LOGGER.info(
                "Connecting to Weight Gurus scale %s via adapter/proxy: %s",
                self.mac,
                service_info.source,
            )

            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.mac, connectable=True
            ) or service_info.device

            if not ble_device:
                _LOGGER.warning(
                    "Could not obtain connectable BLEDevice for %s", self.mac
                )
                return

            client: BleakClient | None = None
            received_data_event = asyncio.Event()

            def notification_handler(
                char: BleakGATTCharacteristic, data: bytearray
            ) -> None:
                """Handle incoming GATT notifications or indications."""
                _LOGGER.debug(
                    "Received notification on %s: %s (hex: %s)",
                    char.uuid,
                    list(data),
                    data.hex(),
                )
                self._parse_gatt_payload(char.uuid.lower(), bytes(data))
                received_data_event.set()

            try:
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    name=self.name,
                    max_attempts=3,
                )

                _LOGGER.debug("Connected to %s. Discovering services...", self.mac)

                # Look for matching characteristics
                subscribed_any = False
                command_char: BleakGATTCharacteristic | None = None

                for service in client.services:
                    for char in service.characteristics:
                        char_uuid = char.uuid.lower()

                        if char_uuid in [u.lower() for u in ALL_WEIGHT_CHARACTERISTICS]:
                            _LOGGER.debug("Subscribing to Weight Characteristic: %s", char_uuid)
                            await client.start_notify(char, notification_handler)
                            subscribed_any = True

                        elif char_uuid in [u.lower() for u in ALL_BODY_CHARACTERISTICS]:
                            _LOGGER.debug("Subscribing to Body Characteristic: %s", char_uuid)
                            await client.start_notify(char, notification_handler)
                            subscribed_any = True

                        elif char_uuid in [u.lower() for u in ALL_COMMAND_CHARACTERISTICS]:
                            command_char = char

                if not subscribed_any:
                    _LOGGER.warning(
                        "No recognized Weight or Body characteristics found on %s. Services: %s",
                        self.mac,
                        [s.uuid for s in client.services],
                    )

                # Send sync/timestamp command if command characteristic is present
                if command_char is not None and "write" in command_char.properties:
                    try:
                        timestamp_payload = b"\x02" + struct.pack("<I", int(time.time()))
                        _LOGGER.debug(
                            "Writing timestamp sync to %s: %s",
                            command_char.uuid,
                            timestamp_payload.hex(),
                        )
                        await client.write_gatt_char(command_char, timestamp_payload, response=False)
                    except Exception as err:
                        _LOGGER.debug("Command write optional step returned: %s", err)

                # Wait for measurement data to arrive
                try:
                    await asyncio.wait_for(received_data_event.wait(), timeout=8.0)
                    _LOGGER.info("Successfully received measurement data from %s", self.mac)
                except asyncio.TimeoutError:
                    _LOGGER.debug("Timeout waiting for notifications from %s", self.mac)

                # Acknowledge receipt if command characteristic exists
                if command_char is not None and received_data_event.is_set():
                    try:
                        ack_payload = b"\x20"
                        await client.write_gatt_char(command_char, ack_payload, response=False)
                    except Exception:
                        pass

            except Exception as err:
                _LOGGER.error("Error communicating with Weight Gurus scale %s: %s", self.mac, err)
            finally:
                if client is not None and client.is_connected:
                    try:
                        await client.disconnect()
                        _LOGGER.debug("Disconnected cleanly from %s", self.mac)
                    except Exception as err:
                        _LOGGER.debug("Disconnect error: %s", err)

            if received_data_event.is_set():
                self._async_notify_listeners()

    def _parse_gatt_payload(self, char_uuid: str, data: bytes) -> None:
        """Parse raw byte arrays into measurement properties."""
        if not data:
            return

        now = datetime.now(timezone.utc)
        self.last_measurement = now

        # Standard Weight Measurement characteristic (0x2A9D)
        if char_uuid == UUID_STANDARD_WEIGHT_MEASUREMENT.lower():
            try:
                flags = data[0]
                is_lbs = bool(flags & 0x01)
                raw_val = int.from_bytes(data[1:3], "little")
                if is_lbs:
                    self.weight_lbs = round(raw_val * 0.01, 1)
                    self.weight_kg = round(self.weight_lbs * 0.45359237, 2)
                else:
                    self.weight_kg = round(raw_val * 0.005, 2)
                    self.weight_lbs = round(self.weight_kg * 2.20462262, 1)
                self._calculate_bmi()
                return
            except Exception as err:
                _LOGGER.debug("Standard weight measurement parse error: %s", err)

        # Transtek / Weight Gurus Weight characteristic (0x8A24)
        if char_uuid in (UUID_WG_WEIGHT.lower(), UUID_TRANSTEK_WEIGHT.lower()):
            try:
                # Format: byte 0 validation (0x1D or 0x1E), bytes 1-2 raw weight, bytes 5-8 timestamp
                if len(data) >= 3:
                    raw_val = int.from_bytes(data[1:3], "little")
                    # If raw_val > 3000, value is typically in 10g increments (e.g. 7500 = 75.00kg)
                    if raw_val > 500:
                        self.weight_kg = round(raw_val / 100.0, 2)
                    else:
                        self.weight_kg = round(raw_val / 10.0, 2)
                    self.weight_lbs = round(self.weight_kg * 2.20462262, 1)
                    self._calculate_bmi()
                    return
            except Exception as err:
                _LOGGER.debug("Weight Gurus weight parse error: %s", err)

        # Transtek / Weight Gurus Body composition characteristic (0x8A22)
        if char_uuid in (UUID_WG_BODY.lower(), UUID_TRANSTEK_BODY.lower()):
            try:
                # Byte 0 is often 0x6F. Unpack body fat, water, muscle if payload length sufficient
                if len(data) >= 12:
                    # Parse fat, water, muscle (0.1% resolution)
                    fat_raw = int.from_bytes(data[6:8], "little") if len(data) >= 8 else None
                    water_raw = int.from_bytes(data[8:10], "little") if len(data) >= 10 else None
                    muscle_raw = int.from_bytes(data[10:12], "little") if len(data) >= 12 else None

                    if fat_raw and 30 <= fat_raw <= 600:
                        self.body_fat = round(fat_raw * 0.1, 1)
                    if water_raw and 200 <= water_raw <= 800:
                        self.water_percentage = round(water_raw * 0.1, 1)
                    if muscle_raw and 200 <= muscle_raw <= 800:
                        self.muscle_percentage = round(muscle_raw * 0.1, 1)
                    return
            except Exception as err:
                _LOGGER.debug("Weight Gurus body composition parse error: %s", err)

    def _calculate_bmi(self) -> None:
        """Calculate BMI if weight and height are known."""
        if self.weight_kg and self.height_cm and self.height_cm > 0:
            height_m = self.height_cm / 100.0
            self.bmi = round(self.weight_kg / (height_m * height_m), 1)
