from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
import asyncio

SWITCH_TYPES = [
    ("power_state", "Spa Power"),
    ("filter_state", "Filter"),
    ("heater_state", "Heater"),
    ("hydrojet_state", "Hydrojet"),
    ("wave_state", "Bubbles / Wave")
]

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    device_id = entry.title.lower().replace(' ', '_')
    async_add_entities([
        BestwaySpaSwitch(coordinator, api, key, name, entry.title, device_id)
        for key, name in SWITCH_TYPES
    ])

class BestwaySpaSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, api, key, name, title, device_id):
        super().__init__(coordinator)
        self._api = api
        self._key = key
        self._attr_name = f"{title} {name}"
        self._attr_unique_id = f"{device_id}_{key}"
        self._device_id = device_id

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._attr_name.split(" ")[0],  # lub np. self._device_id
            "manufacturer": "Bestway",
            "model": "Spa",
            "sw_version": "1.0"
        }
        
    @property
    def is_on(self):
        if self._key == "filter_state":
            # API returns 2 when filter is active
            return self.coordinator.data.get("filter_state") == 2
        elif self._key == "heater_state":
            # API returns 2,4,5,6 when heater is in various heating phases
            heater_state = self.coordinator.data.get("heater_state")
            return heater_state != 0
        elif self._key == "wave_state":
            return self.coordinator.data.get("wave_state", 0) != 0
        else:
            return self.coordinator.data.get(self._key) == 1
            
    @property
    def extra_state_attributes(self):
        if self._key == "wave_state":
            niveau = self.coordinator.data.get("wave_state", 0)
            if niveau == 0:
                mode = "off"
            elif niveau == 100:
                mode = "L1"
            else:
                mode = "L2"
            return {
                "niveau_bulles": mode,
                "valeur_wave_state": niveau
            }
        return {}


    async def async_turn_on(self, **kwargs):
        await self._api.set_state(self._key, 1)
        await asyncio.sleep(2)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self._api.set_state(self._key, 0)
        await asyncio.sleep(2)
        await self.coordinator.async_request_refresh()
