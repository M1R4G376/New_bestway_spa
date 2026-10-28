from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from datetime import timedelta
from .const import AUTH_ACCOUNT, AUTH_LEGACY, CONF_AUTH_METHOD, DOMAIN
from .spa_api import BestwayAccountAPI, BestwayApiError, BestwayAuthError, BestwaySpaAPI, authenticate
import logging

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch", "number", "sensor", "climate", "select", "button"]
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bestway Spa from a config entry."""

    session = async_get_clientsession(hass)

    if entry.data.get(CONF_AUTH_METHOD, AUTH_LEGACY) == AUTH_ACCOUNT:
        api = BestwayAccountAPI(session, entry.data)
        try:
            await api.login()
        except BestwayAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except BestwayApiError as err:
            raise ConfigEntryNotReady(str(err)) from err
    else:
        token = await authenticate(session, entry.data)
        if not token:
            _LOGGER.error("Authentication failed: No token returned")
            return False

        api = BestwaySpaAPI(session, {**entry.data, "token": token})

    async def async_update_data():
        try:
            return await api.get_status()
        except BestwayAuthError as err:
            # Password changed / account removed: ask the user to log in again
            raise ConfigEntryAuthFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(f"Error fetching spa data: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Bestway Spa",
        update_method=async_update_data,
        update_interval=timedelta(seconds=60),
    )

    await coordinator.async_config_entry_first_refresh()

    if not coordinator.last_update_success:
        return False

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
