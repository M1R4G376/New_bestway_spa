## Bestway Smart Spa (Custom Component)

This Home Assistant integration allows you to control your Bestway SmartHub-enabled spa via the Bestway cloud API.

---

## Installation


[![HACS Installation](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=M1R4G376&repository=New_bestway_spa)

## Prerequisites

### Required Equipment
- A **PC or Mac** with [Charles Proxy](https://www.charlesproxy.com/download/) installed
- Two smartphones (Android or iOS):
  - **Phone A**: with the Bestway Smart Hub app installed and already connected to your spa (used to share the QR code)
  - **Phone B**: used to capture traffic through Charles Proxy (the SSL certificate will be installed on this device)

## On Phone B you must use an older version of the application (Bestway Connect 1.0.4) which you can download from APKPURE in order to be able to sniff the traffic.


### Network
- PC and both smartphones must be connected to the **same Wi-Fi network**

---

## Step 1 – Setup Charles Proxy

1. Launch **Charles Proxy** on your PC
2. Go to `Proxy > Proxy Settings` and note the HTTP port (default: `8888`)
3. Go to `Help > SSL Proxying > Install Charles Root Certificate` (install it on your PC)

---

## Step 2 – Configure Phone B

### A. Set Wi-Fi Proxy
- On **Phone B**, go to Wi-Fi settings
- Long press the connected network > Modify > Advanced options
- Set Proxy to **Manual**:
  - **Proxy host**: your PC’s IP address
  - **Port**: `8888`

### B. Install SSL Certificate
> Required to decrypt HTTPS traffic

#### Android
- Visit `http://charlesproxy.com/getssl` on Phone B
Phone will show an error, like Not connected to internet.
Check the PC, Charles proxy is showing a dialog to accept the connection -> Click Allow.
- Download the certificate
- Install it: `Settings > Security > Encryption & credentials > Install from storage`.

Older Android phone: Lock screen and security -> Other security settings -> (section Credential storage) -> Install from device storage -> select the "getssl.crt" file -> Select Used for VPN and Apps (other option is For WiFi)

#### iOS
- Open Safari: [https://chls.pro/ssl](https://chls.pro/ssl)
- Accept and install the profile
- Go to: `Settings > General > VPN & Device Management > Charles Proxy CA`
- Enable in: `Settings > General > About > Certificate Trust Settings`

---

## Step 3 – Enable SSL Proxying

In Charles:
1. Go to `Proxy > SSL Proxying Settings`
2. Select tab "SSL proxy"
Click Plus button
3. Set:
   - Host: `*`
   - Port: `443`

---

## Step 4 – Capture the Data

# ⚠️*It is important to follow these steps in this direction in order to recover all the necessary identifiers.*

1. Start recording in Charles (click the **●** button)
2. Install the Bestway Smart Hub app on **Phone B** >>>> SmartSpa
3. Open the Bestway Smart Hub >>> SmartSpa
4. Select **United Kingdom** 
5. On Phone A open the existing Bestway app, select the device -> 3 dots -> Share the device -> Share the device -> QR code will appear
Scan the QR code with Phone B
Make sure the pairing was successful and you can control the Spa on Phone B
Toggle Pump, Heater, Set temperature, etc, to log them
Stop recording in Charles proxy
Save session in Charles proxy
Analyze recording. Note that Charles requires a license, or it will run only for 30 minutes. You can restart Charles and reload recording.
Watch for requests like thing_shadow, command, or to api.bestwaycorp

Alternatively: rename the recording file from .chlz to .zip and extract all the recorded data. Use Programmer's notepad, Search -> Find -> Find in files; Find what: enter the label we are looking for, for example "device_id", Find where: enter path to extracted files from .zip, File types: "*.json"

Note that a new user will appear on Phone A under Guest users; if you remove it, the HA integration may stop working


---

## Step 5 – Retrieve Credentials

1. Look for a **POST** request to `/enduser/visitor`:
   - [https://smarthub-eu.bestwaycorp.com](https://smarthub-eu.bestwaycorp.com)
2. Open it and check **Request > JSON** or **Text**

### Useful credentials to extract:
- `visitor_id`
- `client_id` (for Android)
- `device_id`
- `product_id`

### Additional:
- `registration_id` and `client_id` can be found in `/api/enduser/visitor`
- `device_id` and `product_id` may be in `/api/enduser/home/room/devices`
- `Registration ID` may be empty or null - in such case type "null" here.
---

## Cleanup

- Disable the proxy on Phone B
- Remove the Charles SSL certificate if no longer needed



---

## Configuration Options

| Field            | Required | Notes                                      |
|------------------|----------|--------------------------------------------|
| `device_name`    | ✅       | Display name in Home Assistant             |
| `visitor_id`     | ✅       | From intercepted app traffic               |
| `registration_id`| ✅       | Same as above                              |
| `client_id`      | ❌       | Only for Android (`push_type = fcm`)       |
| `device_id`      | ✅       | Needed to control the spa                  |
| `product_id`     | ✅       | Needed to control the spa                  |
| `push_type`      | ❌       | `fcm` (Android) or `apns` (iOS), default `fcm` |

---

## API Notes

- `filter_state` returns `2` when active, `0` when off — the integration handles this automatically.
- `select` gives the possibility to choose  the bubble/wave mode OFF/L1/L2 (not available from the official app)
- To **turn on** any feature, the integration sends `1`. To **turn off**, it sends `0`.
- All values are polled from `/api/device/thing_shadow/`

---

## Features

- Toggle spa power, filter, heater, and wave jets
- Adjust water target temperature
- View current water temperature
- Monitor connection status, warnings, and error codes

---

## Example Lovelace Card
![image](https://github.com/user-attachments/assets/e551d76e-e72a-432e-aec0-8da2fa5e751a)

```yaml
type: vertical-stack
cards:
  - type: thermostat
    entity: climate.spa_thermostat
    name: Chauffage Spa
  - type: horizontal-stack
    cards:
      - type: button
        name: Chauffage ON
        icon: mdi:fire
        tap_action:
          action: call-service
          service: climate.set_hvac_mode
          target:
            entity_id: climate.spa_thermostat
          data:
            hvac_mode: heat
      - type: button
        name: Chauffage OFF
        icon: mdi:power
        tap_action:
          action: call-service
          service: climate.set_hvac_mode
          target:
            entity_id: climate.spa_thermostat
          data:
            hvac_mode: "off"
  - type: history-graph
    title: Historique Température Spa
    hours_to_show: 24
    refresh_interval: 60
    entities:
      - entity: sensor.spa_water_temperature
  - type: entities
    title: Commandes Spa
    show_header_toggle: false
    entities:
      - entity: switch.spa_spa_power
        name: Alimentation Spa
        icon: mdi:power
      - entity: switch.spa_filter
        name: Filtration
        icon: mdi:air-filter
      - entity: select.spa_bulles
        name: Bulles
        icon: mdi:chart-bubble

```

## Disclaimer
This is a community-made integration. It is not affiliated with or endorsed by Bestway.
Use at your own risk — the code interacts with a private API which may change.
