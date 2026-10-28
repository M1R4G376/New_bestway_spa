import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    AUTH_ACCOUNT,
    AUTH_LEGACY,
    CONF_AUTH_METHOD,
    CONF_EMAIL,
    CONF_MAC,
    CONF_PASSWORD,
    CONF_PRODUCT_KEY,
    CONF_REGION,
    DOMAIN,
)
from .spa_api import ACCOUNT_ENDPOINTS, BestwayAccountAPI, BestwayApiError, BestwayAuthError

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._account = {}
        self._devices = []

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=["account", "legacy"])

    # ------------------------------------------------------------ account

    async def _login_and_list(self, account):
        """Return (devices, error_key)."""
        api = BestwayAccountAPI(async_get_clientsession(self.hass), account)
        try:
            await api.login()
            devices = await api.list_devices()
        except BestwayAuthError as err:
            _LOGGER.warning("Bestway login failed: %s", err)
            return [], "invalid_auth"
        except BestwayApiError as err:
            _LOGGER.warning("Bestway connection failed: %s", err)
            return [], "cannot_connect"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected error during Bestway login")
            return [], "unknown"
        if not devices:
            # A wrong region logs in fine but returns no device
            return [], "no_devices"
        return devices, None

    async def async_step_account(self, user_input=None):
        errors = {}

        if user_input is not None:
            account = {
                CONF_EMAIL: user_input[CONF_EMAIL].strip(),
                CONF_PASSWORD: user_input[CONF_PASSWORD],
                CONF_REGION: user_input[CONF_REGION],
            }
            devices, error = await self._login_and_list(account)
            if error == "no_devices":
                # Accounts are often registered in another region than expected
                for region in ACCOUNT_ENDPOINTS:
                    if region == account[CONF_REGION]:
                        continue
                    other = {**account, CONF_REGION: region}
                    other_devices, other_error = await self._login_and_list(other)
                    if not other_error:
                        _LOGGER.info("Spa found in region %s instead of %s", region, account[CONF_REGION])
                        account, devices, error = other, other_devices, None
                        break
            if error:
                errors["base"] = error
            else:
                self._account = account
                self._devices = devices
                return await self.async_step_device()

        schema = vol.Schema({
            vol.Required(CONF_EMAIL): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(CONF_REGION, default="EU"): vol.In(list(ACCOUNT_ENDPOINTS)),
        })
        return self.async_show_form(step_id="account", data_schema=schema, errors=errors)

    async def async_step_device(self, user_input=None):
        by_mac = {d["mac"]: d for d in self._devices}

        if user_input is not None:
            device = by_mac[user_input[CONF_MAC]]
            await self.async_set_unique_id(device["mac"])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input["device_name"],
                data={
                    CONF_AUTH_METHOD: AUTH_ACCOUNT,
                    **self._account,
                    CONF_PRODUCT_KEY: device["product_key"],
                    CONF_MAC: device["mac"],
                    "device_name": user_input["device_name"],
                },
            )

        choices = {
            mac: f"{d['name']} ({mac}{'' if d['online'] else ', offline'})"
            for mac, d in by_mac.items()
        }
        first = self._devices[0]
        schema = vol.Schema({
            vol.Required(CONF_MAC, default=first["mac"]): vol.In(choices),
            vol.Required("device_name", default=first["name"]): str,
        })
        return self.async_show_form(step_id="device", data_schema=schema)

    # ------------------------------------------------------------- reauth

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            account = {
                CONF_EMAIL: entry.data[CONF_EMAIL],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
                CONF_REGION: entry.data[CONF_REGION],
            }
            _devices, error = await self._login_and_list(account)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )

    # ------------------------------------------------------------- legacy

    async def async_step_legacy(self, user_input=None):
        errors = {}

        if user_input is not None:
            return self.async_create_entry(
                title=user_input["device_name"],
                data={CONF_AUTH_METHOD: AUTH_LEGACY, **user_input},
            )

        schema = vol.Schema({
            vol.Required("device_name"): str,
            vol.Required("visitor_id"): str,
            vol.Required("registration_id"): str,
            vol.Optional("device_id"): str,
            vol.Optional("product_id"): str,
            vol.Optional("push_type", default="fcm"): vol.In(["fcm", "apns"]),
            vol.Optional("client_id"): str,
            vol.Optional("api_host", default="smarthub-eu.bestwaycorp.com"): str,
            vol.Optional("location", default="GB"): str
        })

        return self.async_show_form(step_id="legacy", data_schema=schema, errors=errors)
