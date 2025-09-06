from homeassistant.const import UnitOfTemperature
from homeassistant.components.number import NumberEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
import asyncio

C_TEMPS = {"min":20, "max":40}
F_TEMPS = {"min":68, "max":104}

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    device_id = entry.title.lower().replace(' ', '_') 
    async_add_entities([
        BestwaySpaTargetTemperature(coordinator, api, entry.title, device_id)
    ])

class BestwaySpaTargetTemperature(CoordinatorEntity, NumberEntity):
    def __init__(self, coordinator, api, title, device_id):
        super().__init__(coordinator)
        self._api = api
        self._attr_name = f"{title} Target Temperature"
        self._attr_unique_id = f"{device_id}_temperature_setting"
        self._device_id = device_id
        self._attr_device_class = "temperature"
        self._attr_native_step = 0.5

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
        return self.coordinator.data.get("temperature_setting")

    @property
    def native_unit_of_measurement(self):
        unit_code = self.coordinator.data.get("temperature_unit", 1)
        return UnitOfTemperature.FAHRENHEIT if unit_code == 0 else UnitOfTemperature.CELSIUS

    @property
    def native_min_value(self):
        unit_code = self.coordinator.data.get("temperature_unit", 1)
        return F_TEMPS["min"] if unit_code == 0 else C_TEMPS["min"]
    
    @property
    def native_max_value(self):
        unit_code = self.coordinator.data.get("temperature_unit", 1)
        return F_TEMPS["max"] if unit_code == 0 else C_TEMPS["max"]

    async def async_set_native_value(self, value: float):
        await self._api.set_state("temperature_setting", value)
        await asyncio.sleep(2)
        await self.coordinator.async_request_refresh()
