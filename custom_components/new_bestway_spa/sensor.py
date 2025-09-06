from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from datetime import datetime, date
from .const import DOMAIN

SENSOR_TYPES = [
    ("water_temperature", "Water Temperature"),
    ("is_online", "Connection Status"),
    ("temperature_unit", "Temperature Unit"),
    ("warning", "Warning"),
    ("error_code", "Error Code"),
    ("hydrojet_state", "Hydrojet"),
    ("connect_type", "Connection Type"),
    ("wifi_version", "WiFi Version"),
    ("ota_status", "OTA Status"),
    ("mcu_version", "MCU Version"),
    ("trd_version", "TRD Version")
]

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    device_id = entry.title.lower().replace(' ', '_')
    sensors = [
        BestwaySpaSensor(coordinator, key, name, entry.title, device_id)
        for key, name in SENSOR_TYPES
    ]
    sensors.extend([
        DaysSinceSensor(coordinator, entry, "Filter", "filter_last_change", device_id),
        DaysSinceSensor(coordinator, entry, "Chlorine", "chlorine_last_add", device_id),
    ])
    async_add_entities(sensors)

class BestwaySpaSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, key, name, title, device_id):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"{title} {name}"
        self._attr_unique_id = f"{device_id}_{key}"
        self._device_id = device_id

        # enable long-term statistics for water temperature
        if self._key == "water_temperature":
            self._attr_device_class = "temperature"
            self._attr_state_class = "measurement"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._attr_name.split(" ")[0],  # lub np. self._device_id
            "manufacturer": "Bestway",
            "model": "Spa",
            "sw_version": self.hass.data[DOMAIN].get("manifest_version", "unknown")
        }

    @property
    def native_value(self):
        if self._key == "temperature_unit":
            raw = self.coordinator.data.get("temperature_unit", 1)
            return UnitOfTemperature.FAHRENHEIT if raw == 0 else UnitOfTemperature.CELSIUS
        return self.coordinator.data.get(self._key)

    @property
    def native_unit_of_measurement(self):
        if self._key == "water_temperature":
            unit_code = self.coordinator.data.get("temperature_unit", 1)
            return UnitOfTemperature.FAHRENHEIT if unit_code == 0 else UnitOfTemperature.CELSIUS
        return None

class DaysSinceSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry, name, key, device_id):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = f"{entry.title} Days Since {name}"
        self._key = key
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_{key}_days_since"
        self._attr_native_unit_of_measurement = UnitOfTime.DAYS
        self._attr_device_class = "duration"
        self._attr_state_class = "total_increasing"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._entry.title,
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
