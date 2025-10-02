from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from datetime import datetime, date
from .const import DOMAIN

SENSOR_TYPES = [
    ("water_temperature", "Water Temperature", "°C"),
    ("is_online", "Connection Status", None),
    ("temperature_unit", "Temperature Unit", None),
    ("warning", "Warning", None),
    ("error_code", "Error Code", None),
    ("hydrojet_state", "Hydrojet", None),
    ("connect_type", "Connection Type", None),
    ("wifi_version", "WiFi Version", None),
    ("ota_status", "OTA Status", None),
    ("mcu_version", "MCU Version", None),
    ("trd_version", "TRD Version", None)
]

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    device_id = entry.title.lower().replace(' ', '_')
    sensors = [
        BestwaySpaSensor(coordinator, key, name, unit, entry.title, device_id)
        for key, name, unit in SENSOR_TYPES
    ]
    sensors.extend([
        DaysSinceSensor(coordinator, entry, "Filter", "filter_last_change", device_id),
        DaysSinceSensor(coordinator, entry, "Chlorine", "chlorine_last_add", device_id),
    ])
    async_add_entities(sensors)

class BestwaySpaSensor(CoordinatorEntity, SensorEntity):
    has_entity_name = True
    def __init__(self, coordinator, key, name, unit, title, device_id):
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = key
        self._attr_translation_placeholders = {"name": f"{title} {name}"}
        self._attr_unique_id = f"{device_id}_{key}"
        self._device_id = device_id
        self._attr_native_unit_of_measurement = unit

        # enable long-term statistics for water temperature
        if self._key == "water_temperature":
            self._attr_device_class = "temperature"
            self._attr_state_class = "measurement"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "translation_key": self._attr_translation_key,
            "translation_placeholders": self._attr_translation_placeholders,
            "manufacturer": "Bestway",
            "model": "Spa",
            "sw_version": self.hass.data[DOMAIN].get("manifest_version", "unknown")
        }

    @property
    def native_value(self):
        if self._key == "temperature_unit":
            raw = self.coordinator.data.get("temperature_unit", 1)
            return "°F" if raw == 0 else "°C" 
        return self.coordinator.data.get(self._key)

    @property
    def native_unit_of_measurement(self):
        if self._key == "water_temperature":
            unit_code = self.coordinator.data.get("temperature_unit", 1)
            return "°F" if unit_code == 0 else "°C"
        return self._attr_native_unit_of_measurement

class DaysSinceSensor(CoordinatorEntity, SensorEntity):
    has_entity_name = True
    def __init__(self, coordinator, entry, name, key, device_id):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_translation_key = key
        self._attr_translation_placeholders = {"name": f"{entry.title} Days Since {name}"}
        self._key = key
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_{key}_days_since"
        self._attr_native_unit_of_measurement = "days"
        self._attr_device_class = "duration"
        self._attr_state_class = "total_increasing"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "translation_key": self._attr_translation_key,
            "translation_placeholders": self._attr_translation_placeholders,
            "manufacturer": "Bestway",
            "model": "Spa",
            "sw_version": self.hass.data[DOMAIN].get("manifest_version", "unknown")
        }

    @property
    def native_value(self):
        stored_date_str = self._entry.data.get(self._key)
        if not stored_date_str:
            return None
        try:
            stored_date = datetime.strptime(stored_date_str, "%Y-%m-%d").date()
            return (date.today() - stored_date).days
        except (ValueError, TypeError):
            return None
