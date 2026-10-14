"""
DataUpdateCoordinator for Starlink Remote - Universal Discovery & Telemetry.

All HTTP traffic goes through a single httpx.Client (HTTP/2) that carries the
browser session cookie harvested from starlink.com. Telemetry is read over the
device gRPC-Web endpoint; the account (webagg) API is used for hardware
discovery. The account-wide data usage figure is *not* part of that payload,
so the router's own client counters are published separately instead.
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import timedelta
from typing import Any

import httpx
from google.protobuf.json_format import MessageToDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import notify, session, storage
from .const import (
    CONF_COOKIE,
    CONF_COOKIE_FILE,
    CONF_SCAN_INTERVAL,
    DATA_DEVICES,
    DATA_USAGE,
    DATA_WIFI_CLIENTS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    STARLINK_API_URL,
    STARLINK_AUTH_URL,
    STARLINK_WEB_SERVICE_LINES,
    UA,
)
from .spacex.api.device.device_pb2 import (
    GetHistoryRequest,
    GetStatusRequest,
    Request,
    Response,
)

_LOGGER = logging.getLogger(__name__)

#: Seconds of continuous 401 responses before the user gets a repair issue.
_AUTH_FAILURE_GRACE = 60

#: Seconds the cached service-lines payload is reused. It carries the hardware
#: inventory, so it does not need a request per poll cycle.
_SERVICE_LINES_TTL = 3600

#: Field names that would carry an account-wide usage counter. Kept so a future
#: portal revision that starts shipping one is picked up without a code change;
#: the payload carries no such field today (verified against the live account).
_USAGE_KEY_HINTS = frozenset(
    {
        "datausagebytes",
        "totalbytesused",
        "bytesused",
        "totalbytes",
        "usagebytes",
        "datausagegb",
        "usagegb",
        "gbused",
        "datagb",
    }
)


#: Bounds for the debug payload skeleton: keeps the diagnostic line small.
_SHAPE_MAX_ENTRIES = 80
_SHAPE_MAX_DEPTH = 7


def _payload_shape(node: Any, prefix: str = "") -> list[str]:
    """Describe a payload as ``path=value`` lines without leaking text values.

    Used when the account API changes shape: the log then shows where the usage
    counter moved to. Only the numbers matter for that, so strings are reported
    as ``str[len]`` - account identifiers stay out of the log.
    """
    entries: list[str] = []

    def walk(value: Any, path: str, depth: int) -> None:
        if len(entries) >= _SHAPE_MAX_ENTRIES or depth > _SHAPE_MAX_DEPTH:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{path}.{key}" if path else str(key), depth + 1)
        elif isinstance(value, (list, tuple)):
            entries.append(f"{path}[] ({len(value)} items)")
            for index, item in enumerate(value[:2]):
                walk(item, f"{path}[{index}]", depth + 1)
        elif isinstance(value, bool) or isinstance(value, (int, float)):
            entries.append(f"{path}={value}")
        elif isinstance(value, str):
            entries.append(f"{path}=str[{len(value)}]")
        elif value is None:
            entries.append(f"{path}=null")
        else:
            entries.append(f"{path}={type(value).__name__}")

    walk(node, prefix, 0)
    return entries


def _as_number(value: Any) -> float | None:
    """Return ``value`` as a float when it is (or looks like) a number.

    Protobuf/JSON serialisers emit large counters as strings to preserve
    precision, so ``"16106127360"`` must be accepted next to 16106127360.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


class StarlinkCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Handle session persistence, hardware discovery and gRPC-Web polling."""

    def __init__(self, hass: HomeAssistant, entry: Any) -> None:
        """Initialize the coordinator."""
        self._entry = entry

        self.discovered_ids: set[str] = set()
        self._saved_ids: set[str] = set()
        self._raw_cookie = ""
        self._saved_cookie = ""
        self._xsrf_token = ""
        self._service_lines: Any = None
        self._service_lines_read_at: float = 0.0

        # Error tracking: how long the account API has been rejecting the
        # session, and whether that was already reported to the user.
        self._auth_failure_start: float | None = None
        self._auth_failure_detail = ""
        self._notification_sent = False
        # Alerts left behind by an earlier process are cleared on the first
        # successful session check (see _handle_auth_success).
        self._alerts_cleared = False

        self._client: httpx.Client | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )

    @property
    def entry_id(self) -> str:
        """Return the id of the config entry this coordinator belongs to.

        Every per-entry identity (entity unique ids, device identifiers, the
        stored cookie, the repair issue and the notification) is derived from
        it, so two entries never share one account's state.
        """
        return self._entry.entry_id

    @property
    def _session_headers(self) -> dict[str, str]:
        """Return the browser-like headers that carry the session cookie."""
        return {
            "User-Agent": UA,
            "cookie": self._raw_cookie,
            "x-xsrf-token": self._xsrf_token,
        }

    async def _async_setup(self) -> None:
        """Load persisted state and prime the session (runs once per setup)."""
        await self.hass.async_add_executor_job(self._init_client_and_load_data)
        await self.hass.async_add_executor_job(self._refresh_session)
        await self.hass.async_add_executor_job(self._discover_hardware)

    async def async_shutdown(self) -> None:
        """Close the HTTP client when the config entry is unloaded."""
        await super().async_shutdown()
        await self.hass.async_add_executor_job(self._close_client)

    def _close_client(self) -> None:
        """Close the persistent HTTP client (SyncWorker)."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def _init_client_and_load_data(self) -> None:
        """Create the HTTP client, restore the metrics and load the cookie.

        SyncWorker: this touches the disk and builds the connection pool.
        """
        if self._client is None:
            # One client for the whole lifetime of the entry, so HTTP/2 keeps
            # the TLS connection to starlink.com open between polls.
            self._client = httpx.Client(http2=True, timeout=15.0, follow_redirects=True)

        self._load_persistent_data()

        # Cookie precedence: the mirrored storage file (kept fresh by the
        # session prime), then a file next to the component for local
        # development, then the value stored in the config entry.
        persisted_cookie = storage.load_cookie(self.hass, self.entry_id)
        self._raw_cookie = persisted_cookie
        # Already on disk: do not rewrite it on the next save.
        self._saved_cookie = persisted_cookie
        source = "storage file" if persisted_cookie else ""

        if not self._raw_cookie:
            dev_cookie_file = os.path.join(os.path.dirname(__file__), CONF_COOKIE_FILE)
            if os.path.exists(dev_cookie_file):
                try:
                    with open(dev_cookie_file, encoding="utf-8") as handle:
                        self._raw_cookie = handle.read().strip()
                    source = "development cookie file"
                except OSError as err:
                    _LOGGER.error("Failed to read the development cookie file: %s", err)

        if not self._raw_cookie:
            self._raw_cookie = self._entry.data.get(CONF_COOKIE, "")
            source = "config entry"

        _LOGGER.debug("Session cookie loaded from the %s", source or "nowhere")

        self._sync_cookies_to_client()

    def _sync_cookies_to_client(self) -> None:
        """Inject the raw cookie string into the httpx.Client jar."""
        if not self._raw_cookie or not self._client:
            return
        session.apply_cookie(self._client, self._raw_cookie)
        self._xsrf_token = session.xsrf_token(self._client, self._raw_cookie)

    def _load_persistent_data(self) -> None:
        """Restore the hardware ids discovered on earlier runs (SyncWorker)."""
        self.discovered_ids |= storage.load_discovered_ids(self.hass, self.entry_id)
        self._saved_ids = set(self.discovered_ids)

    def _save_persistent_data(self) -> None:
        """Persist the discovered hardware ids and a rotated cookie (SyncWorker)."""
        # Both writes are guarded by a change check: the previous version
        # rewrote the files on every poll, i.e. once a minute.
        if self.discovered_ids != self._saved_ids:
            storage.save_discovered_ids(self.hass, self.entry_id, self.discovered_ids)
            self._saved_ids = set(self.discovered_ids)

        if self._raw_cookie and self._raw_cookie != self._saved_cookie:
            storage.save_cookie(self.hass, self.entry_id, self._raw_cookie)
            self._saved_cookie = self._raw_cookie

    def _refresh_session(self) -> bool:
        """Execute the session priming cycle."""
        if not self._client:
            return False
        try:
            headers = self._session_headers
            response_home = self._client.get(
                "https://www.starlink.com/account/home", headers=headers
            )
            response_auth = self._client.get(STARLINK_AUTH_URL, headers=headers)

            if {response_home.status_code, response_auth.status_code} & {401, 403}:
                self._handle_auth_failure(
                    f"The account API answered HTTP {response_home.status_code} "
                    f"for the session probe and HTTP {response_auth.status_code} "
                    f"for the auth check."
                )
                return False

            # Diagnostic: a 200 alone does not prove the session is valid, the
            # page may simply be the sign-in shell. These four numbers are what
            # distinguishes a live session from a stale cookie in the logs.
            _LOGGER.debug(
                "Session probe: account/home=%s (%s bytes, final url %s), "
                "auth-rp=%s (%s bytes), cookie jar=%s entries",
                response_home.status_code,
                len(response_home.content),
                response_home.url,
                response_auth.status_code,
                len(response_auth.content),
                len(self._client.cookies.jar),
            )

            self._handle_auth_success()

            new_jar = "; ".join(
                f"{cookie.name}={cookie.value}" for cookie in self._client.cookies.jar
            )
            if new_jar:
                self._raw_cookie = new_jar
                self._xsrf_token = self._client.cookies.get(
                    "XSRF-TOKEN", domain=".starlink.com", default=self._xsrf_token
                )
                self._save_persistent_data()
            _LOGGER.debug(
                "Session refreshed successfully (%s cookies in the jar)",
                len(self._client.cookies.jar),
            )
            return True
        except httpx.HTTPError as err:
            _LOGGER.debug("Session refresh failed: %s", err, exc_info=True)
            return False

    def _handle_auth_failure(self, detail: str = "") -> None:
        """Track consecutive auth failures and alert the user past the grace period."""
        now = time.time()
        if self._auth_failure_start is None:
            self._auth_failure_start = now
            self._auth_failure_detail = detail

        if self._notification_sent:
            return
        if now - self._auth_failure_start < _AUTH_FAILURE_GRACE:
            return

        _LOGGER.warning(
            "Starlink session invalid for over %s seconds, alerting the user",
            _AUTH_FAILURE_GRACE,
        )
        self._notification_sent = True
        # This runs in a SyncWorker thread, so the alerts have to be handed to
        # the event loop through add_job(). Both the repair issue and the
        # notification belong to this entry only.
        self.hass.add_job(
            notify.async_raise_session_alerts,
            self.hass,
            self._entry,
            self._auth_failure_detail,
        )

    def _handle_auth_success(self) -> None:
        """Forget the failure window and drop the alerts of this entry."""
        self._auth_failure_start = None
        self._auth_failure_detail = ""
        if not (self._notification_sent or not self._alerts_cleared):
            return

        # Two cases: the session recovered after an alert was raised, or the
        # first check after a restart found a leftover alert from the previous
        # process (Home Assistant or the entry was reloaded while the cookie
        # was already broken).
        self._notification_sent = False
        self._alerts_cleared = True
        self.hass.add_job(
            notify.async_clear_session_alerts, self.hass, self._entry
        )

    def _fetch_service_lines(self, *, force: bool = False) -> None:
        """Fetch and cache the webagg service-lines payload (SyncWorker).

        The payload carries the account-wide usage figure that the per-device
        gRPC polls cannot produce. It is a monthly counter, so it is cached for
        ``_SERVICE_LINES_TTL`` and refreshed even when device discovery is not
        needed.
        """
        if not self._client:
            return
        if (
            not force
            and self._service_lines is not None
            and time.time() - self._service_lines_read_at < _SERVICE_LINES_TTL
        ):
            return

        try:
            response = self._client.get(
                STARLINK_WEB_SERVICE_LINES, headers=self._session_headers
            )
        except httpx.HTTPError as err:
            _LOGGER.debug("Service-lines fetch failed: %s", err, exc_info=True)
            return

        if response.status_code != 200:
            _LOGGER.debug("Service-lines fetch returned HTTP %s", response.status_code)
            return

        try:
            self._service_lines = response.json()
        except ValueError as err:
            _LOGGER.debug("Service-lines payload is not JSON: %s", err)
            return
        self._service_lines_read_at = time.time()

    def _discover_hardware(self) -> None:
        """Dynamically identify Dishes and Routers."""
        if not self._client:
            return
        headers = self._session_headers

        self._fetch_service_lines(force=True)
        if self._service_lines is not None:
            for result in self._service_lines.get("content", {}).get("results", []):
                for terminal in result.get("userTerminals", []):
                    if terminal_id := terminal.get("userTerminalId"):
                        self.discovered_ids.add(f"ut{terminal_id}")
                    for router in terminal.get("routers", []):
                        if router_id := router.get("routerId"):
                            self.discovered_ids.add(f"Router-{router_id}")

        try:
            response = self._client.get("https://www.starlink.com/account/home", headers=headers)
            if response.status_code == 200:
                found = set(re.findall(r"Router-[A-Fa-f0-9]{24}", response.text))
                found.update(re.findall(r"ut[a-f0-9-]{36}", response.text))
                found.update(re.findall(r"selectedDevice=([A-Fa-f0-9-]+)", response.text))
                self.discovered_ids.update(found)
        except httpx.HTTPError as err:
            _LOGGER.debug("Account page discovery failed: %s", err, exc_info=True)

        if self.discovered_ids:
            self._save_persistent_data()

    def _find_usage_entry(self, node: Any, path: str = "") -> tuple[str, float] | None:
        """Return the first (path, value) whose key looks like a usage counter."""
        if isinstance(node, dict):
            for key, value in node.items():
                child = f"{path}.{key}" if path else str(key)
                if str(key).lower().replace("_", "") in _USAGE_KEY_HINTS:
                    number = _as_number(value)
                    if number is not None:
                        return child, number
                found = self._find_usage_entry(value, child)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for index, item in enumerate(node):
                found = self._find_usage_entry(item, f"{path}[{index}]")
                if found is not None:
                    return found
        return None

    @staticmethod
    def _usage_to_gb(path: str, value: float) -> float:
        """Convert a usage counter to GB, deducing the unit from key and magnitude."""
        if path.lower().replace("_", "").endswith(("gb", "gbused")):
            return round(value, 3)
        if value >= 1024**2:  # plainly a byte counter
            return round(value / 1024**3, 3)
        return round(value, 3)

    def _account_data_usage(self) -> dict[str, Any] | None:
        """Return the account-wide data usage from the cached webagg payload.

        Verified against the live account: the service-lines payload that the
        cookie-authenticated webagg API returns carries no usage counter at all
        (subscription flags and hardware inventory only), and the billing-period
        figure on starlink.com/account/home comes from a request the portal makes
        outside this API. The scan is kept for a future API revision, but until
        one ships a counter the caller publishes the router's own client totals
        under a separate key rather than presenting them as the account total.
        """
        payload = self._service_lines
        if payload is None:
            return None

        found = self._find_usage_entry(payload)
        if found is not None:
            path, value = found
            _LOGGER.debug("Account data usage read from %s", path)
            return {"total_gb": self._usage_to_gb(path, value)}

        _LOGGER.debug(
            "No data usage counter in the service-lines payload; keys seen: %s; shape: %s",
            sorted(payload)[:25] if isinstance(payload, dict) else type(payload).__name__,
            _payload_shape(payload),
        )
        return None

    async def _async_update_data(self) -> dict[str, Any]:
        """Perform the periodic update cycle."""
        await self.hass.async_add_executor_job(self._refresh_session)
        if not self.discovered_ids:
            await self.hass.async_add_executor_job(self._discover_hardware)
        else:
            # Without this the usage figure is only ever read during setup and
            # would sit at 0.0 for the lifetime of the entry.
            await self.hass.async_add_executor_job(self._fetch_service_lines)
        return await self.hass.async_add_executor_job(self._fetch_all)

    def _fetch_all(self) -> dict[str, Any]:
        """Poll telemetry using gRPC-Web binary tunneling."""
        if not self._client:
            return {DATA_DEVICES: {}}

        data: dict[str, Any] = {DATA_DEVICES: {}}
        all_clients: list[dict[str, Any]] = []
        headers = {
            **self._session_headers,
            "origin": "https://www.starlink.com",
            "referer": "https://www.starlink.com/account/home",
            "content-type": "application/grpc-web+proto",
            "x-grpc-web": "1",
        }

        for target_id in list(self.discovered_ids):
            device_type = "dish" if target_id.startswith("ut") else "router"
            device_data: dict[str, Any] = {
                "status": {},
                "history": {},
                "type": device_type,
            }
            try:
                # 1. STATUS
                response = self._client.post(
                    STARLINK_API_URL,
                    headers=headers,
                    content=self._grpc_web_frame(
                        Request(target_id=target_id, get_status=GetStatusRequest())
                    ),
                )

                if response.status_code == 401:
                    self._handle_auth_failure()

                if response.status_code == 200 and len(response.content) > 5:
                    self._handle_auth_success()
                    message = self._grpc_web_message(response.content, Response)
                    response_type = message.WhichOneof("response") if message else None
                    if response_type:
                        raw = MessageToDict(
                            getattr(message, response_type), preserving_proto_field_name=True
                        )
                        device_data["status"] = raw
                        device_data["status"]["state"] = "CONNECTED"
                        _LOGGER.debug(
                            "Status response for %s: type=%s keys=%s",
                            target_id,
                            response_type,
                            sorted(raw)[:25],
                        )
                        if response_type == "wifi_get_status":
                            # The router's status response carries no client
                            # list on api_version 129, and every dedicated
                            # client request (wifi_get_clients,
                            # wifi_get_client_history, wifi_get_ping_metrics)
                            # answers "Unimplemented" or empty. The list is
                            # therefore only published when a future firmware
                            # starts reporting it - the sensor stays "unknown"
                            # rather than claiming zero clients.
                            clients = raw.get("clients") or []
                            if clients:
                                device_data[DATA_WIFI_CLIENTS] = clients
                                all_clients.extend(clients)

                # 2. HISTORY
                response_history = self._client.post(
                    STARLINK_API_URL,
                    headers=headers,
                    content=self._grpc_web_frame(
                        Request(target_id=target_id, get_history=GetHistoryRequest())
                    ),
                )

                if response_history.status_code == 200 and len(response_history.content) > 5:
                    message_history = self._grpc_web_message(response_history.content, Response)
                    response_type_history = (
                        message_history.WhichOneof("response") if message_history else None
                    )
                    if response_type_history:
                        device_data["history"] = MessageToDict(
                            getattr(message_history, response_type_history),
                            preserving_proto_field_name=True,
                        )

                data[DATA_DEVICES][target_id] = device_data
                _LOGGER.debug("Poll succeeded for %s (%s)", target_id, device_type)
            except Exception as err:  # pylint: disable=broad-except
                # Per-poll transport failures are routine (a device can be
                # offline or the session stale): keep the log quiet and let the
                # entities show the gap, the user is warned once via the
                # repair issue instead.
                _LOGGER.debug("Poll failed for %s: %s", target_id, err)

        if all_clients:
            data[DATA_WIFI_CLIENTS] = all_clients
        usage = self._account_data_usage()
        if usage is not None:
            data[DATA_USAGE] = usage

        # The service-lines payload carries no usage counter (verified against
        # the live account), so no account-wide number can be published: the
        # account usage sensor stays "unknown" rather than showing a zero that
        # looks like a real reading.

        return data

    @staticmethod
    def _grpc_web_frame(request: Any) -> bytes:
        """Wrap a protobuf request in a gRPC-Web length-prefixed frame."""
        serialized = request.SerializeToString()
        return b"\x00" + len(serialized).to_bytes(4, "big") + serialized

    @staticmethod
    def _grpc_web_message(content: bytes, message_class: Any) -> Any | None:
        """Parse the protobuf message out of a gRPC-Web response body."""
        if len(content) <= 5:
            return None
        message_length = int.from_bytes(content[1:5], "big")
        message = message_class()
        message.ParseFromString(content[5 : 5 + message_length])
        return message

    async def async_send_command(
        self, target_id: str, request_field: str, request_data: Any
    ) -> bool:
        """Send a gRPC command to a specific device."""
        return await self.hass.async_add_executor_job(
            self._send_command, target_id, request_field, request_data
        )

    def _send_command(self, target_id: str, request_field: str, request_data: Any) -> bool:
        """Execute a gRPC command (SyncWorker)."""
        if not self._client:
            return False
        from .spacex.api.device.device_pb2 import Request

        try:
            headers = {
                **self._session_headers,
                "origin": "https://www.starlink.com",
                "referer": "https://www.starlink.com/account/home",
                "content-type": "application/grpc-web+proto",
                "x-grpc-web": "1",
            }
            response = self._client.post(
                STARLINK_API_URL,
                headers=headers,
                content=self._grpc_web_frame(
                    Request(**{request_field: request_data, "target_id": target_id})
                ),
            )
            _LOGGER.debug(
                "%s sent to %s (status %s)", request_field, target_id, response.status_code
            )
            return response.status_code == 200
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error("%s failed for %s: %s", request_field, target_id, err)
            return False
