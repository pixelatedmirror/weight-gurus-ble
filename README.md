# Weight Gurus BLE Home Assistant Integration

A local, offline Home Assistant integration for **Weight Gurus (Greater Goods)** Bluetooth smart scales, including **Model 0383** and **Model 0376** (Transtek OEM).

No cloud account, smartphone app, or internet connection is required.

---

## Features

- **100% Local & Offline**: Communicates directly with the scale via Bluetooth Low Energy (BLE).
- **Home Assistant Bluetooth Discovery**: Automatically detects your scale when you step on it via any local Bluetooth adapter or **ESPHome Bluetooth Proxy**.
- **Metrics Tracked**:
  - Weight (kg / lbs based on Home Assistant unit preferences)
  - Body Fat (%)
  - Body Water (%)
  - Muscle Mass (%)
  - BMI (calculated from height)
  - Last Measurement Timestamp
  - Signal Strength (RSSI)
- **Wake-on-Step**: Keeps battery consumption at zero until you step on the scale. When awakened, the integration connects, captures the measurement, confirms receipt (making the scale beep and clear pending syncs), and immediately disconnects.

---

## Installation via HACS

1. In Home Assistant, open **HACS** > **Integrations**.
2. Click the three dots in the top right corner and select **Custom repositories**.
3. Add the repository URL:
   `https://github.com/pixelatedmirror/weight-gurus-ble`
4. Set the category to **Integration** and click **Add**.
5. Find **Weight Gurus BLE** in HACS and click **Download**.
6. Restart Home Assistant.

---

## Setup & Pairing

1. Ensure Bluetooth is configured in Home Assistant (via a local Bluetooth dongle or an ESPHome active Bluetooth proxy with `bluetooth_proxy: active: true`).
2. Step onto your Weight Gurus scale with bare feet.
3. The scale will wake up and flash the Bluetooth icon.
4. Home Assistant will discover the scale and display a notification in **Settings** > **Devices & Services**.
5. Click **Configure**, enter your height (used to calculate BMI), and submit.

### Manual Configuration
If discovery does not pop up automatically:
1. Go to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for **Weight Gurus BLE**.
3. Select your scale from the list of discovered Bluetooth devices or enter its MAC address manually.

---

## Hardware Compatibility

- **Weight Gurus Model 0383** (Bluetooth Smart Scale)
- **Weight Gurus Model 0376** (Bluetooth Smart Scale V2)
- **Greater Goods GBF-1719 series**
- Scales adhering to standard Bluetooth SIG Weight Scale Service (`0x181D`)
