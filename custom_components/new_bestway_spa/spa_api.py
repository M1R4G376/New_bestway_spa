import logging
import hashlib
import random
import string
import time
import aiohttp

_LOGGER = logging.getLogger(__name__)


async def authenticate(session, config):
    api_host = config.get("api_host", "smarthub-eu.bestwaycorp.com")
    BASE_URL = "https://" + api_host
    APPID = "AhFLL54HnChhrxcl9ZUJL6QNfolTIB"
    APPSECRET = "4ECvVs13enL5AiYSmscNjvlaisklQDz7vWPCCWXcEFjhWfTmLT"

    def generate_auth():
        nonce = ''.join(random.choices(string.ascii_lowercase + string.digits, k=32))
        ts = str(int(time.time()))
        sign = hashlib.md5((APPID + APPSECRET + nonce + ts).encode("utf-8")).hexdigest().upper()
        return nonce, ts, sign

    push_type = config.get("push_type", "fcm")

    payload = {
        "app_id": APPID,
        "lan_code": "en",
        "location": config.get("location", "GB"),
        "push_type": push_type,
        "timezone": "GMT",
        "visitor_id": config["visitor_id"],
        "registration_id": config["registration_id"]
    }

    if push_type == "fcm":
        payload["client_id"] = config["client_id"]

    nonce, ts, sign = generate_auth()
    headers = {
        "pushtype": push_type,
        "appid": APPID,
        "nonce": nonce,
        "ts": ts,
        "accept-language": "en",
        "sign": sign,
        "Authorization": "token",
        "Host": api_host,
        "Connection": "Keep-Alive",
        "User-Agent": "okhttp/4.9.0",
        "Content-Type": "application/json; charset=UTF-8"
    }

    _LOGGER.debug("Authenticating with payload: %s", payload)

    async with session.post(
        f"{BASE_URL}/api/enduser/visitor",
        headers=headers,
        json=payload,
        ssl=False
    ) as resp:
        data = await resp.json()
        _LOGGER.debug("Auth response: %s", data)
        return data.get("data", {}).get("token")


class BestwaySpaAPI:
    APPID = "AhFLL54HnChhrxcl9ZUJL6QNfolTIB"
    APPSECRET = "4ECvVs13enL5AiYSmscNjvlaisklQDz7vWPCCWXcEFjhWfTmLT"

    def __init__(self, session: aiohttp.ClientSession, config: dict):
        self.api_host = config.get("api_host", "smarthub-eu.bestwaycorp.com")
        self.BASE_URL = "https://" + self.api_host
        self.session = session
        self.token = config["token"]
        self.device_id = config.get("device_id") or config["device_name"]
        self.product_id = config.get("product_id") or config["device_name"]
        self.client_id = config.get("client_id")
        self.registration_id = config.get("registration_id")
        self.push_type = config.get("push_type", "fcm")

    def _generate_auth_headers(self):
        nonce = ''.join(random.choices(string.ascii_lowercase + string.digits, k=32))
        ts = str(int(time.time()))
        sign = hashlib.md5((self.APPID + self.APPSECRET + nonce + ts).encode("utf-8")).hexdigest().upper()
        return {
            "pushtype": self.push_type,
            "appid": self.APPID,
            "nonce": nonce,
            "ts": ts,
            "accept-language": "en",
            "sign": sign,
            "Authorization": f"token {self.token}",
            "Host": self.api_host,
            "Connection": "Keep-Alive",
            "User-Agent": "okhttp/4.9.0",
            "Content-Type": "application/json; charset=UTF-8"
        }

    async def get_status(self):
        payload = {
            "device_id": self.device_id,
            "product_id": self.product_id
        }

        _LOGGER.debug("Sending get_status payload: %s", payload)

        async with self.session.post(
            f"{self.BASE_URL}/api/device/thing_shadow/",
            headers=self._generate_auth_headers(),
            json=payload,
            ssl=False
        ) as resp:
            data = await resp.json()
            _LOGGER.debug("Full API response: %s", data)

            raw_data = data.get("data", {})
            _LOGGER.debug("Raw data from API: %s", raw_data)

            if "state" in raw_data:
                if "reported" in raw_data["state"]:
                    device_state = raw_data["state"]["reported"]
                    _LOGGER.debug("Found reported state: %s", device_state)
                elif "desired" in raw_data["state"]:
                    device_state = raw_data["state"]["desired"]
                    _LOGGER.debug("Found desired state: %s", device_state)
                else:
                    device_state = raw_data["state"]
                    _LOGGER.debug("Found state object: %s", device_state)
            else:
                device_state = raw_data

            # ✅ Normalize keys to match sensor keys
            mapped = {
                "wifi_version": device_state.get("wifivertion"),
                "ota_status": device_state.get("otastatus"),
                "mcu_version": device_state.get("mcuversion"),
                "trd_version": device_state.get("trdversion"),
                "connect_type": device_state.get("ConnectType"),
                "power_state": device_state.get("power_state"),
                "heater_state": device_state.get("heater_state"),
                "wave_state": device_state.get("wave_state"),
                "filter_state": device_state.get("filter_state"),
                "temperature_setting": device_state.get("temperature_setting"),
                "temperature_unit": device_state.get("temperature_unit"),
                "water_temperature": device_state.get("water_temperature"),
                "warning": device_state.get("warning"),
                "error_code": device_state.get("error_code"),
                "hydrojet_state": device_state.get("hydrojet_state"),
                "is_online": device_state.get("is_online")
            }

            _LOGGER.debug("Normalized data: %s", mapped)
            return mapped

    async def set_state(self, key, value):
        if isinstance(value, bool):
            value = int(value)

        payload = {
            "device_id": self.device_id,
            "product_id": self.product_id,
            "desired": {
                "state": {
                    "desired": {
                        key: value
                    }
                }
            }
        }

        _LOGGER.debug("Sending set_state payload: %s", payload)

        async with self.session.post(
            f"{self.BASE_URL}/api/device/command/",
            headers=self._generate_auth_headers(),
            json=payload,
            ssl=False
        ) as resp:
            response = await resp.json()
            _LOGGER.debug("set_state response: %s", response)
            return response
