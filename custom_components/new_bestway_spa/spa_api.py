import asyncio
import base64
import json
import logging
import hashlib
import random
import string
import time
import aiohttp

_LOGGER = logging.getLogger(__name__)


def _unwrap_shadow(raw_data):
    """Return the flat datapoint dict from a shadow ({state: {reported: ...}} or flat)."""
    if not isinstance(raw_data, dict):
        return {}

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
    return device_state


def normalize_shadow(raw_data):
    """Map a device shadow (legacy or account gateway) to the entity keys."""
    device_state = _unwrap_shadow(raw_data)

    if _is_v01_shadow(device_state):
        mapped = _normalize_v01(device_state)
        _LOGGER.debug("Normalized data (V01 vocabulary): %s", mapped)
        return mapped

    is_online = device_state.get("is_online")
    connect_type = device_state.get("ConnectType")
    if is_online is None and connect_type is not None:
        is_online = str(connect_type).lower() == "online"

    # ✅ Normalize keys to match sensor keys
    mapped = {
        "wifi_version": device_state.get("wifivertion"),
        "ota_status": device_state.get("otastatus"),
        "mcu_version": device_state.get("mcuversion"),
        "trd_version": device_state.get("trdversion"),
        "connect_type": connect_type,
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
        "is_online": is_online
    }

    _LOGGER.debug("Normalized data: %s", mapped)
    return mapped



# ---------------------------------------------------------------------------
# V01 vocabulary (older Lay-Z-Spa Airjet_V01 / Hydrojet, e.g. Toronto, issue #36)
#
# Some spas report Gizwits-style datapoints instead of the V02 names:
#   power, heat, filter, wave, jet, Tnow, Tset, Tunit, E01..E32
# Semantics as in cdpuk/ha-bestway (translation.py): heat 0=off, 4=target
# reached, other=heating; Tunit 0=F else C; E32 is not an error.
# ---------------------------------------------------------------------------

_V01_MARKERS = ("Tnow", "Tset", "heat")
_E_CODE_KEYS = [f"E{i:02d}" for i in range(1, 33)]

# entity key -> V01 datapoint used for writes
_V01_WRITE_KEYS = {
    "power_state": "power",
    "heater_state": "heat",
    "filter_state": "filter",
    "wave_state": "wave",
    "hydrojet_state": "jet",
    "temperature_setting": "Tset",
}
# V01 "on" values (cdpuk HydrojetHeat.ON = 3, HydrojetFilter.ON = 2)
_V01_ON_VALUES = {"heat": 3, "filter": 2, "power": 1, "jet": 1}


def _is_v01_shadow(state):
    return isinstance(state, dict) and any(k in state for k in _V01_MARKERS) \
        and "water_temperature" not in state


def _int_or_none(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_v01(state):
    power = state.get("power")
    filt = _int_or_none(state.get("filter"))
    tunit = state.get("Tunit")
    errors = [k for k in _E_CODE_KEYS if k != "E32" and state.get(k)]
    return {
        "wifi_version": None,
        "ota_status": None,
        "mcu_version": None,
        "trd_version": None,
        "connect_type": None,
        "power_state": None if power is None else int(bool(power)),
        "heater_state": _int_or_none(state.get("heat")),
        "wave_state": _int_or_none(state.get("wave")),
        # switch.py treats 2 as "filtering"
        "filter_state": None if filt is None else (2 if filt else 0),
        "temperature_setting": _int_or_none(state.get("Tset")),
        "temperature_unit": None if tunit is None else (0 if _int_or_none(tunit) == 0 else 1),
        "water_temperature": _int_or_none(state.get("Tnow")),
        "warning": None,
        "error_code": ",".join(errors) if errors else 0,
        "hydrojet_state": None if state.get("jet") is None else int(bool(state.get("jet"))),
        "is_online": True,
    }


def _to_v01_command(key, value):
    """Translate an entity write into the V01 datapoint, or None if unknown."""
    v01_key = _V01_WRITE_KEYS.get(key)
    if v01_key is None:
        return None
    if v01_key == "Tset":
        return v01_key, int(value)
    if v01_key == "wave":
        # 0 = off; the select sends 1 to step levels, use 100 (max) for "on"
        value = int(value)
        return v01_key, (0 if value == 0 else (value if value > 1 else 100))
    return v01_key, (_V01_ON_VALUES[v01_key] if value else 0)

# ---------------------------------------------------------------------------
# Account login (Bestway Connect app, email + password)
#
# Since the Bestway Connect update of July 2026 the app talks to a new gateway
# (smart-spa-{eu,us,cn}-app.bestwaycorp.com) that accepts a regular user
# account. Protocol documented by jimsawinner/ha-bestway (MIT):
#   POST app/smart_home/login/pwd               -> data.userToken
#   GET  app/smart_home/users/devices           -> devices on the account
#   GET  app/device/shadow/{productKey}/{mac}   -> state
#   POST app/device/control/{productKey}/{mac}  -> command ("data" = JSON *string*)
# Responses look like {"code": "200", "message": ..., "data": ...}; code "505"
# means the token is no longer valid.
# ---------------------------------------------------------------------------

ACCOUNT_APP_ID = "39ef26ff404a4cb1b5652f336d4bc045"

ACCOUNT_ENDPOINTS = {
    "EU": "https://smart-spa-eu-app.bestwaycorp.com",
    "US": "https://smart-spa-us-app.bestwaycorp.com",
    "CN": "https://smart-spa-cn-app.bestwaycorp.com",
}

ACCOUNT_TIMEOUT = 20

# State keys the gateway expects as plain 1/0 on write (some read back as 2).
_BINARY_KEYS = ("power_state", "filter_state", "heater_state", "wave_state", "hydrojet_state")


class BestwayAuthError(Exception):
    """Wrong credentials or session that cannot be renewed."""


class BestwayApiError(Exception):
    """Any other gateway error."""


def _content_md5(body):
    return base64.b64encode(hashlib.md5(body.encode("utf-8")).digest()).decode()


def _envelope(data):
    return {"appKey": ACCOUNT_APP_ID, "data": data, "version": "1.0"}


def _first(entry, *keys):
    for key in keys:
        if entry.get(key) not in (None, ""):
            return entry[key]
    return None


_PRODUCT_KEY_KEYS = ("productKey", "product_key", "productkey", "pk")
_MAC_KEYS = ("mac", "deviceMac", "device_mac", "macAddress", "did")
_SECRET_KEYS = {"userToken", "token", "refreshToken", "password", "uid", "openId", "passcode"}


def _walk_dicts(obj):
    """Yield every dict found in a nested JSON structure."""
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk_dicts(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_dicts(value)


def _scrub(obj):
    """Hide tokens/ids before logging."""
    if isinstance(obj, dict):
        return {k: ("***" if k in _SECRET_KEYS else _scrub(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


class BestwayAccountAPI:
    """Client for the account gateway, same interface as BestwaySpaAPI."""

    def __init__(self, session: aiohttp.ClientSession, config: dict):
        self.session = session
        self.region = config.get("region", "EU")
        self.base_url = ACCOUNT_ENDPOINTS.get(self.region, ACCOUNT_ENDPOINTS["EU"])
        self.email = config["email"]
        self.password = config["password"]
        self.product_key = config.get("product_key")
        self.mac = (config.get("mac") or "").lower()
        self.token = None
        self.v01 = False

    def _headers(self, body):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json; charset=utf-8",
            "Version": "1.0",
            "date": "null",
            "X-Gizwits-Application-Id": ACCOUNT_APP_ID,
        }
        if body is not None:
            headers["Content-MD5"] = _content_md5(body)
        if self.token:
            # Bare token, not "Bearer <token>"
            headers["Authorization"] = self.token
        return headers

    async def _send(self, method, path, body_obj=None):
        body = json.dumps(body_obj, separators=(",", ":")) if body_obj is not None else None
        try:
            async with asyncio.timeout(ACCOUNT_TIMEOUT):
                async with self.session.request(
                    method,
                    f"{self.base_url}/{path}",
                    data=body.encode("utf-8") if body is not None else None,
                    headers=self._headers(body),
                ) as resp:
                    if resp.status == 401:
                        return {"code": "505"}
                    return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise BestwayApiError(f"{method} {path}: {err}") from err

    async def login(self):
        """Log in with email/password and store the user token."""
        self.token = None
        result = await self._send(
            "POST",
            "app/smart_home/login/pwd",
            _envelope({
                "account": self.email,
                "password": self.password,
                "lang": "en",
                "refreshToken": True,
            }),
        )
        data = result.get("data")
        token = data.get("userToken") if isinstance(data, dict) else None
        if str(result.get("code")) != "200" or not token:
            # Never log the password
            raise BestwayAuthError(f"Login failed (code {result.get('code')}): {result.get('message')}")
        self.token = token
        _LOGGER.debug("Bestway account login OK")

    async def _request(self, method, path, body_obj=None):
        """Request with a single transparent re-login if the token expired."""
        if not self.token:
            await self.login()

        for attempt in (1, 2):
            result = await self._send(method, path, body_obj)
            code = str(result.get("code", ""))
            if code == "200":
                return result
            if code == "505" and attempt == 1:
                _LOGGER.info("Bestway token rejected, logging in again")
                await self.login()
                continue
            raise BestwayApiError(f"{method} {path} failed (code {code}): {result.get('message')}")

        raise BestwayAuthError("Re-authentication did not yield a valid session")

    async def list_devices(self):
        """Return [{"product_key", "mac", "name", "online"}] for the account."""
        result = await self._request("GET", "app/smart_home/users/devices")
        data = result.get("data")
        _LOGGER.debug("Device list response: %s", data)

        # Shape not fully documented (flat list, wrapped list, or nested under
        # homes/rooms): collect every dict carrying a productKey and a mac.
        devices = []
        seen = set()
        for entry in _walk_dicts(data):
            product_key = _first(entry, *_PRODUCT_KEY_KEYS)
            mac = _first(entry, *_MAC_KEYS)
            if not product_key or not mac or str(mac).lower() in seen:
                continue
            seen.add(str(mac).lower())
            devices.append({
                "product_key": str(product_key),
                "mac": str(mac).lower(),
                "name": str(_first(entry, "name", "alias", "deviceName", "nickname", "remark", "productName") or "Spa"),
                "online": bool(_first(entry, "onlineStatus", "isOnline", "is_online", "online")),
            })

        if not devices:
            # Visible without debug logging, so users can report the shape
            _LOGGER.warning(
                "No spa found in the Bestway device list (region %s). Response: %s",
                self.region, json.dumps(_scrub(data), ensure_ascii=False)[:2000],
            )
        return devices

    async def get_status(self):
        result = await self._request("GET", f"app/device/shadow/{self.product_key}/{self.mac}")
        _LOGGER.debug("Full API response: %s", result)
        data = result.get("data")
        self.v01 = _is_v01_shadow(_unwrap_shadow(data))
        return normalize_shadow(data)

    async def set_state(self, key, value):
        if isinstance(value, bool):
            value = int(value)
        if self.v01:
            command = _to_v01_command(key, value)
            if command is not None:
                key, value = command
        elif key in _BINARY_KEYS:
            value = 1 if value else 0

        # "data" MUST be a JSON string: an object returns 200 and does nothing.
        payload = _envelope(json.dumps({key: value}, separators=(",", ":")))
        _LOGGER.debug("Sending set_state payload: %s", payload)
        response = await self._request("POST", f"app/device/control/{self.product_key}/{self.mac}", payload)
        _LOGGER.debug("set_state response: %s", response)
        return response


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

            return normalize_shadow(raw_data)

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
