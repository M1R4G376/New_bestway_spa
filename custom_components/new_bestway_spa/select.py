import asyncio
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

OPTIONS = ["Off", "L1", "L2"]

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Bestway Spa bubble mode select entity."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    device_id = entry.title.lower().replace(' ', '_')
    async_add_entities([BestwaySpaBubbleSelect(coordinator, api, entry.title, device_id)])


class BestwaySpaBubbleSelect(CoordinatorEntity, SelectEntity):
    """Select entity to control the bubble mode of the Bestway Spa."""
    has_entity_name = True
    _attr_options = OPTIONS

    def __init__(self, coordinator, api, title, device_id):
        super().__init__(coordinator)
        self._api = api
        self._attr_translation_key = "bubble_mode"
        self._attr_translation_placeholders = {"name": f"{title} Bubbles"}
        self._attr_unique_id = f"{device_id}_bubble_mode"
        self._device_id = device_id

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
    def current_option(self):
        """Return the current bubble mode based on wave_state."""
        wave_state = self.coordinator.data.get("wave_state", 0)
        _LOGGER.debug(f"Current wave_state: {wave_state}")

        if wave_state == 0:
            return "Off"
        elif wave_state == 100:
            return "L1"
        else:
            return "L2"

    async def async_select_option(self, option: str):
        """Handle selection from user."""
        _LOGGER.debug(f"User selected bubble mode: {option}")

        if option == "Off":
            await self._api.set_state("wave_state", 0)

        elif option == "L1":
            await self._api.set_state("wave_state", 0)
            await asyncio.sleep(1.5)
            await self._api.set_state("wave_state", 1)

        elif option == "L2":
            await self._api.set_state("wave_state", 0)
            await asyncio.sleep(1.5)
            await self._api.set_state("wave_state", 1)
            await asyncio.sleep(1.5)
            await self._api.set_state("wave_state", 1)

        await self.coordinator.async_request_refresh()

__all__ = ["async_setup_entry"]
