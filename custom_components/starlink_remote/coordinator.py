"""
DataUpdateCoordinator for Starlink Remote - Universal Discovery & Telemetry.

All HTTP traffic goes through a single httpx.Client (HTTP/2) that carries the
browser session cookie harvested from starlink.com. Telemetry is read over the
device gRPC-Web endpoint; the account APIs are used for hardware discovery,
for the account-wide data usage figure (a telemetry aggregate reports it once
per billing cycle) and for the routers' Wi-Fi client counts, which the
per-device gRPC polls do not expose on api_version 129.
"""
from __future__ import annotations

import csv
import io
import logging
import os
import re
import struct
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from google.protobuf.json_format import MessageToDict
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.ssl import get_default_context

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
    STARLINK_DATA_USAGE_EXPORT,
    STARLINK_DEVICE_TELEMETRY,
    STARLINK_PORTAL_HOME,
    STARLINK_TELEMETRYAGG_DATA_USAGE,
    STARLINK_TOKEN_REFRESH,
    STARLINK_WEB_SERVICE_LINES,
    UA,
    USAGE_SOURCE_ANNOTATED,
    USAGE_SOURCE_EXPORT,
    USAGE_SOURCE_TELEMETRY,
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


#: gRPC-Web request kinds this integration is allowed to send. The two reads
#: are the poll; ``reboot`` is the single write the user keeps available. Stow,
#: unstow, factory reset and every configuration write are refused here and are
#: not implemented anywhere in the component.
ALLOWED_GRPC_REQUESTS = frozenset({"get_status", "get_history", "reboot"})

#: The power series added by newer dish firmware: a repeated float field in the
#: history message, one sample per second, 15 minutes = 900 values. The schema
#: shipped here predates the field, so it is found by shape rather than number:
#: an unknown length-delimited field whose payload is 600-1200 plausible watts.
POWER_SAMPLE_MIN = 600
POWER_SAMPLE_MAX = 1200
POWER_VALUE_MAX = 400.0

#: Bounds for the debug payload skeleton: keeps the diagnostic line small.
_SHAPE_MAX_ENTRIES = 80
_SHAPE_MAX_DEPTH = 7


def _read_varint(buffer: bytes, position: int) -> tuple[int, int]:
    """Read a protobuf varint; returns ``(value, new_position)``."""
    result = shift = 0
    while True:
        byte = buffer[position]
        position += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, position
        shift += 7


def development_cookie_file() -> str:
    """Return the cookie file used when neither storage nor the entry has one.

    ``STARLINK_REMOTE_COOKIE_FILE`` points it outside the source tree, which is
    how the development environment keeps a real cookie out of the repository;
    without the variable the historical location next to the component is used.
    """
    return os.environ.get("STARLINK_REMOTE_COOKIE_FILE") or os.path.join(
        os.path.dirname(__file__), CONF_COOKIE_FILE
    )


def _parse_datetime(value: Any) -> datetime | None:
    """Return an ISO timestamp from an account payload as an aware datetime."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _as_count(value: Any) -> int | None:
    """Return ``value`` as an int for a counter, or None when it is not one."""
    number = _as_number(value)
    return int(number) if number is not None else None


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
        elif isinstance(value, (bool, int, float)):
            entries.append(f"{path}={value}")
        elif isinstance(value, str):
            entries.append(f"{path}=str[{len(value)}]")
        elif value is None:
            entries.append(f"{path}=null")
        else:
            entries.append(f"{path}={type(value).__name__}")

    walk(node, prefix, 0)
    return entries


def _device_state(status: dict[str, Any]) -> str:
    """Return the state of a device, as far as the API reports one.

    This surface has no CONNECTED/SEARCHING enum: the dish answers with a
    disablement code (``OKAY`` when nothing disables it) and the router's own
    ``state`` field is unset on api_version 129. A code other than OKAY is the
    signal worth surfacing - BOOTING, STOWED, THERMAL_SHUTDOWN and so on - and
    is reported verbatim rather than flattened into CONNECTED.
    """
    code = status.get("disablement_code") or status.get("state")
    if isinstance(code, str) and code and code.upper() != "OKAY":
        return code
    return "CONNECTED"


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


#: Billing-cycle fields that carry the total directly, most authoritative first.
#: ``totalAmountGB`` is what the portal writes today; the others are checked so a
#: payload that renames or moves the figure still resolves.
_CYCLE_TOTAL_KEYS = ("totalAmountGB", "totalUsageGB", "usageAmountGB", "totalGB")

#: Key fragments that mark a number as a cap or a remainder, never as usage.
_CAP_KEY_FRAGMENTS = ("limit", "cap", "allowance", "remaining")

#: Key fragments that mark a number as a usage amount.
_USAGE_KEY_FRAGMENTS = ("gb", "amount", "usage", "used")


def _is_usage_key(key: str) -> bool:
    """Return True when ``key`` names a usage amount rather than a cap."""
    lowered = key.lower()
    if any(fragment in lowered for fragment in _CAP_KEY_FRAGMENTS):
        return False
    return any(fragment in lowered for fragment in _USAGE_KEY_FRAGMENTS)


def _daily_usage_values(cycle: dict[str, Any]) -> list[float]:
    """Return the per-day usage numbers of one billing cycle, in report order."""
    values: list[float] = []
    for row in cycle.get("dailyData") or []:
        raw = row[0] if isinstance(row, list) and row else row
        if isinstance(raw, dict):
            raw = next(
                (item for key, item in raw.items() if _is_usage_key(str(key))), None
            )
        number = _as_number(raw)
        if number is not None:
            values.append(round(number, 3))
    return values


def _sum_usage_lines(rows: Any) -> float | None:
    """Sum the usage amounts of ``dataUsageSummaryLines``, None when there are none.

    Only usage keys count: ``usageLimitGB`` is the cap of the bucket, not the
    amount used, so summing the line verbatim would report the plan instead.
    """
    total = 0.0
    seen = False
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            if not _is_usage_key(str(key)):
                continue
            number = _as_number(value)
            if number is None or number < 0:
                continue
            total += number
            seen = True
    return round(total, 3) if seen else None


def _cycle_usage_gb(cycle: dict[str, Any]) -> tuple[float | None, str]:
    """Return the usage of one billing cycle and the field it was read from.

    The annotated payload carries the cycle total in ``totalAmountGB`` for the
    accounts seen so far. An account that bills more than one data bucket keeps
    the per-bucket figures in ``dataUsageSummaryLines`` and the per-day series in
    ``dailyData``; when the cycle total is missing or zero those are summed
    instead, so such an account does not read as a flat zero. A cycle that
    genuinely has no usage still reports 0.
    """
    reported = _as_number(cycle.get("totalAmountGB"))
    if reported:
        return reported, "totalAmountGB"
    for key in _CYCLE_TOTAL_KEYS[1:]:
        value = _as_number(cycle.get(key))
        if value:
            return value, key
    lines_total = _sum_usage_lines(cycle.get("dataUsageSummaryLines"))
    if lines_total:
        return lines_total, "dataUsageSummaryLines"
    daily_total = sum(_daily_usage_values(cycle))
    if daily_total > 0:
        return round(daily_total, 3), "dailyData"
    # Nothing in the cycle reports usage: keep whatever it did carry, so an
    # idle cycle stays 0 rather than becoming unknown.
    if reported is not None:
        return reported, "totalAmountGB"
    if lines_total is not None:
        return lines_total, "dataUsageSummaryLines"
    if daily_total == 0 and cycle.get("dailyData"):
        return 0.0, "dailyData"
    return None, ""


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
        # Last successfully read account data usage: the figure is a monthly
        # counter, so it is kept when a poll cannot read it (see the update loop).
        self._last_usage: dict[str, Any] | None = None
        # Accumulated dish energy, in Wh, integrated from the history series.
        self._energy_wh: float = 0.0
        self._energy_last_ts: float = 0.0
        self._energy_saved: float = 0.0
        # Which source last produced a usable figure (see _account_data_usage).
        self._usage_source: str | None = None

        # Error tracking: how long the account API has been rejecting the
        # session, and whether that was already reported to the user.
        self._auth_failure_start: float | None = None
        self._auth_failure_detail = ""
        self._notification_sent = False
        # Alerts left behind by an earlier process are cleared on the first
        # successful session check (see _handle_auth_success).
        self._alerts_cleared = False

        self._client: httpx.Client | None = None
        # Bearer token minted from the SSO cookie; the cookie's access tokens
        # expire long before the session does (see _refresh_bearer).
        self._bearer_token: str = ""
        self._bearer_valid_until: float = 0.0

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
        """Return the headers that carry the session (cookie + bearer token)."""
        headers = {
            "User-Agent": UA,
            "cookie": self._raw_cookie,
            "x-xsrf-token": self._xsrf_token,
        }
        if self._bearer_token and time.time() < self._bearer_valid_until:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        return headers

    def _refresh_bearer(self) -> bool:
        """Mint a bearer token from the SSO cookie (SyncWorker).

        The access cookies the browser hands out expire within minutes while the
        SSO session stays valid; the web app calls this endpoint to keep working,
        and both the REST APIs and gRPC-Web accept the resulting token. Without
        it, a perfectly good session shows up as ``token_expired``.
        """
        if not self._client or not self._raw_cookie:
            return False
        try:
            response = self._client.get(
                STARLINK_TOKEN_REFRESH,
                headers={
                    "User-Agent": UA,
                    "cookie": self._raw_cookie,
                    "accept": "application/json",
                    "origin": "https://starlink.com",
                    "referer": "https://starlink.com/account/home",
                },
            )
        except httpx.HTTPError as err:
            _LOGGER.debug("Token refresh failed: %s", err, exc_info=True)
            return False
        if response.status_code != 200:
            _LOGGER.debug("Token refresh returned HTTP %s", response.status_code)
            return False
        try:
            payload = response.json()
        except ValueError:
            _LOGGER.debug("Token refresh body is not JSON")
            return False
        token = payload.get("accessToken")
        if not isinstance(token, str) or len(token) < 20:
            _LOGGER.debug("Token refresh carried no access token")
            return False
        try:
            lifetime = int(payload.get("expiresIn") or 0)
        except (TypeError, ValueError):
            lifetime = 0
        self._bearer_token = token
        # Renew a minute early so a poll never races the expiry.
        self._bearer_valid_until = time.time() + max(lifetime - 60, 30)
        _LOGGER.debug("Minted a bearer token valid for %s s", lifetime)
        return True

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send a request, refreshing the bearer token once when it expired."""
        if self._client is None:
            raise RuntimeError("HTTP client is not initialised")
        headers = {**self._session_headers, **kwargs.pop("headers", {})}
        response = self._client.request(method, url, headers=headers, **kwargs)
        if self._auth_lost(response) and self._refresh_bearer():
            headers = {**self._session_headers, **kwargs.pop("headers", {})}
            response = self._client.request(method, url, headers=headers, **kwargs)
        return response

    def _auth_lost(self, response: httpx.Response) -> bool:
        """Return True when a response says the access token is not accepted."""
        if response.status_code == 401:
            return True
        return "token_expired" in response.text[:200]

    async def _async_setup(self) -> None:
        """Load persisted state and prime the session (runs once per setup)."""
        await self.hass.async_add_executor_job(self._init_client_and_load_data)
        await self.hass.async_add_executor_job(self._refresh_bearer)
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
            self._client = httpx.Client(
                http2=True,
                timeout=15.0,
                follow_redirects=True,
                verify=get_default_context(),
            )

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
            dev_cookie_file = development_cookie_file()
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
        energy_wh, last_ts = storage.load_energy(self.hass, self.entry_id)
        self._energy_wh = energy_wh
        self._energy_saved = energy_wh
        self._energy_last_ts = last_ts

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

        if round(self._energy_wh, 3) != round(self._energy_saved, 3):
            storage.save_energy(
                self.hass, self.entry_id, self._energy_wh, self._energy_last_ts
            )
            self._energy_saved = self._energy_wh

    def _refresh_session(self) -> bool:
        """Execute the session priming cycle."""
        if not self._client:
            return False
        try:
            headers = self._session_headers
            response_home = self._client.get(STARLINK_PORTAL_HOME, headers=headers)
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

        if self._auth_lost(response) and self._refresh_bearer():
            response = self._client.get(
                STARLINK_WEB_SERVICE_LINES, headers=self._session_headers
            )
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
            response = self._client.get(STARLINK_PORTAL_HOME, headers=headers)
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

    def _service_line_ids(self) -> tuple[str, str] | None:
        """Return the account reference id and first service line number.

        Used where the API is account-scoped (telemetry); the data-usage reader
        uses :meth:`_all_service_line_ids` instead.
        """
        ids = self._all_service_line_ids()
        return ids[0] if ids else None

    def _all_service_line_ids(self) -> list[tuple[str, str]]:
        """Return the account reference id and service line of every line.

        An account can hold several service lines; reading only the first one
        under-reported the total for those accounts, which is one of the
        reasons users saw a wrong or missing figure.
        """
        if not self._service_lines:
            return []
        results = (self._service_lines.get("content") or {}).get("results") or []
        ids: list[tuple[str, str]] = []
        for result in results:
            account = result.get("accountReferenceId")
            service_line = result.get("serviceLineNumber")
            if account and service_line:
                ids.append((str(account), str(service_line)))
        return ids

    @staticmethod
    def _current_billing_cycle(
        cycles: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Return the billing cycle that contains now, else the most recent."""
        parsed: list[tuple[datetime, datetime, dict[str, Any]]] = []
        for cycle in cycles:
            start = _parse_datetime(cycle.get("startDate"))
            end = _parse_datetime(cycle.get("endDate"))
            if start is not None and end is not None:
                parsed.append((start, end, cycle))
        if not parsed:
            return cycles[-1] if cycles else None
        now = datetime.now(UTC)
        for start, end, cycle in parsed:
            if start <= now < end:
                return cycle
        # No cycle covers now: a portal revision may reorder the list or leave the
        # dates unparsable. The most recently started cycle is the best answer,
        # taking the last element would depend on the order the API happens to use.
        return max(parsed, key=lambda item: item[0])[2]

    def _usage_from_annotated(self) -> dict[str, Any] | None:
        """Read the billing-cycle total from the annotated aggregate.

        This is the source the integration has always used: one entry per
        billing cycle for one service line, with a total, the plan buckets
        and a per-day series.

        The figure the Starlink app shows under "Data usage" is an account
        value: the annotated aggregate answers with one entry per billing cycle,
        each carrying the total consumed in that cycle plus a per-day
        breakdown. Read from the account API only - the per-device gRPC polls
        cannot produce it and the service-lines payload does not hold it.
        """
        ids = self._all_service_line_ids()
        if not self._client or not ids:
            return None
        readings = [
            self._usage_for_service_line(account, service_line)
            for account, service_line in ids
        ]
        readings = [reading for reading in readings if reading is not None]
        if not readings:
            return None
        usage = readings[0]
        if len(readings) > 1:
            usage = dict(usage)
            usage["total_gb"] = round(sum(item["total_gb"] for item in readings), 3)
            usage["lines"] = len(readings)
            _LOGGER.debug(
                "Data usage: %.3f GB summed over %d service lines",
                usage["total_gb"],
                len(readings),
            )
        return usage

    def _usage_for_service_line(
        self, account: str, service_line: str
    ) -> dict[str, Any] | None:
        """Return the annotated usage of one service line, or None.

        Raises nothing: an account with several lines keeps the lines that
        answered instead of losing the whole figure to one failing line.
        """
        if not self._client:
            return None
        try:
            response = self._request(
                "GET",
                STARLINK_TELEMETRYAGG_DATA_USAGE.format(
                    account=account, service_line=service_line
                ),
            )
        except httpx.HTTPError as err:
            _LOGGER.debug("Data usage fetch failed: %s", err, exc_info=True)
            return None

        if response.status_code == 401:
            self._handle_auth_failure()
            return None
        if response.status_code != 200:
            _LOGGER.debug("Data usage fetch returned HTTP %s", response.status_code)
            return None
        try:
            payload = response.json()
        except ValueError as err:
            _LOGGER.debug("Data usage payload is not JSON: %s", err)
            return None

        content = payload.get("content") or {}
        cycle = self._current_billing_cycle(
            content.get("billingCyclesAnnotated") or []
        )
        if cycle is None:
            _LOGGER.debug(
                "Data usage payload holds no billing cycle; keys seen: %s",
                sorted(content)[:25],
            )
            return None

        total, source = _cycle_usage_gb(cycle)
        if total is None:
            _LOGGER.debug(
                "Data usage: the current billing cycle carries no usage counter; "
                "payload shape: %s",
                _payload_shape(content),
            )
            return None
        if not total:
            _LOGGER.debug(
                "Data usage: the current billing cycle reports 0 GB; cycle shape: %s",
                _payload_shape(cycle),
            )

        lines = cycle.get("dataUsageSummaryLines") or []
        buckets = content.get("dataBuckets") or []
        names: list[str] = []
        limits: list[float] = []
        for line in lines:
            if not isinstance(line, dict):
                continue
            index = line.get("dataBucketIndex") or 0
            if 0 <= index < len(buckets):
                name = buckets[index].get("name")
                if name and name not in names:
                    names.append(name)
            if (limit := _as_number(line.get("usageLimitGB"))) and limit > 0:
                limits.append(limit)
        bucket = ", ".join(names) or None
        limit = sum(limits) if limits else None
        daily = _daily_usage_values(cycle)
        _LOGGER.debug(
            "Data usage: %.3f GB (read from %s) between %s and %s (%s day(s) reported)",
            total,
            source,
            cycle.get("startDate"),
            cycle.get("endDate"),
            len(daily),
        )
        return {
            "total_gb": round(total, 3),
            "source": USAGE_SOURCE_ANNOTATED,
            "field": source,
            "limit_gb": round(limit, 3) if limit else None,
            "bucket": bucket,
            "cycle_start": cycle.get("startDate"),
            "cycle_end": cycle.get("endDate"),
            "daily_gb": daily,
            "lines": 1,
        }

    def _usage_from_telemetry(
        self, telemetry: dict[str, dict[str, Any]] | None
    ) -> dict[str, Any] | None:
        """Read the account byte counters out of the telemetry snapshot.

        The snapshot carries a per-account row (device type ``d``) with
        ``DownlinkBytes``/``UplinkBytes`` and the billing day. It is the only
        cloud figure available when the aggregate refuses an account, so it is
        the second source in the chain.
        """
        if not telemetry:
            return None
        for record in telemetry.values():
            downlink = _as_number(record.get("DownlinkBytes"))
            uplink = _as_number(record.get("UplinkBytes"))
            if downlink is None and uplink is None:
                continue
            total_bytes = (downlink or 0.0) + (uplink or 0.0)
            if total_bytes <= 0:
                continue
            billing_day = record.get("BillingDayOfMonth")
            _LOGGER.debug(
                "Data usage: %.3f GB from the telemetry byte counters (billing day %s)",
                total_bytes / 1024**3,
                billing_day,
            )
            return {
                "total_gb": round(total_bytes / 1024**3, 3),
                "source": USAGE_SOURCE_TELEMETRY,
                "field": "DownlinkBytes+UplinkBytes",
                "limit_gb": None,
                "bucket": record.get("ProductId"),
                "cycle_start": None,
                "cycle_end": None,
                "daily_gb": [],
            }
        return None

    def _usage_from_export(self) -> dict[str, Any] | None:
        """Read consumed data blocks from the CSV export, when it has them.

        The export is a per-block table. Its exact columns vary by account, so
        the parser looks for a header that names a consumed amount in GB and
        ignores capacity/limit columns; no such column means no figure.
        """
        ids = self._service_line_ids()
        if not self._client or ids is None:
            return None
        account, _ = ids

        try:
            response = self._request(
                "GET",
                STARLINK_DATA_USAGE_EXPORT.format(account=account),
                headers={"accept": "text/csv"},
            )
        except httpx.HTTPError as err:
            _LOGGER.debug("Data-usage export failed: %s", err, exc_info=True)
            return None
        if response.status_code != 200 or not response.text.strip():
            _LOGGER.debug("Data-usage export returned HTTP %s", response.status_code)
            return None

        rows = list(csv.reader(io.StringIO(response.text)))
        if len(rows) < 2:
            return None
        header = [column.strip().lower() for column in rows[0]]
        index = None
        # The live export names the column "TotalBlockConsumedGB": "total" here
        # means the block total, not a cap, so only cap-like words exclude a
        # column.
        for position, column in enumerate(header):
            if any(word in column for word in ("capacity", "limit", "remaining", "allowance")):
                continue
            if "gb" in column and any(word in column for word in ("used", "consumed", "usage")):
                index = position
                break
        if index is None:
            _LOGGER.debug("Data-usage export has no consumed-GB column: %s", header)
            return None

        total = 0.0
        seen = False
        for row in rows[1:]:
            if index >= len(row):
                continue
            number = _as_number(row[index])
            if number is None or number < 0:
                continue
            total += number
            seen = True
        if not seen:
            return None
        _LOGGER.debug("Data usage: %.3f GB from the data-block export", total)
        return {
            "total_gb": round(total, 3),
            "source": USAGE_SOURCE_EXPORT,
            "field": header[index],
            "limit_gb": None,
            "bucket": None,
            "cycle_start": None,
            "cycle_end": None,
            "daily_gb": [],
        }

    def _account_data_usage(
        self, telemetry: dict[str, dict[str, Any]] | None = None
    ) -> dict[str, Any] | None:
        """Return the data usage from the first source that answers (SyncWorker).

        The annotated aggregate stays first and keeps working exactly as
        before; the telemetry counters and the data-block export are only
        consulted when it returns nothing usable. The source that answered is
        remembered and tried first on the next poll, so an account does not pay
        for two failing requests every cycle.
        """
        readers = [
            (USAGE_SOURCE_ANNOTATED, self._usage_from_annotated),
            (USAGE_SOURCE_TELEMETRY, lambda: self._usage_from_telemetry(telemetry)),
            (USAGE_SOURCE_EXPORT, self._usage_from_export),
        ]
        if self._usage_source:
            readers.sort(key=lambda item: item[0] != self._usage_source)

        for name, reader in readers:
            try:
                usage = reader()
            except Exception as err:  # one source must not break the poll
                _LOGGER.debug("Data-usage source %s failed: %s", name, err, exc_info=True)
                continue
            if usage is None or usage.get("total_gb") is None:
                continue
            if name != self._usage_source:
                _LOGGER.info("Data usage is read from the %s source", name)
                self._usage_source = name
            return usage

        _LOGGER.debug("No data-usage source answered this poll")
        return None

    def _cloud_telemetry(self) -> dict[str, dict[str, Any]]:
        """Return the account telemetry snapshot, keyed by reported device id.

        Routers publish their Wi-Fi client counts here, per band and over
        ethernet, together with the WAN counters. The per-device gRPC polls
        return no client list on api_version 129 and the counts belong to the
        account, so no local network access is involved.
        """
        ids = self._service_line_ids()
        if not self._client or ids is None:
            return {}
        account, _ = ids

        try:
            response = self._request(
                "POST",
                STARLINK_DEVICE_TELEMETRY,
                json={"accountNumber": account},
            )
        except httpx.HTTPError as err:
            _LOGGER.debug("Telemetry fetch failed: %s", err, exc_info=True)
            return {}

        if response.status_code == 401:
            self._handle_auth_failure()
            return {}
        if response.status_code != 200:
            _LOGGER.debug("Telemetry fetch returned HTTP %s", response.status_code)
            return {}
        try:
            payload = response.json()
        except ValueError as err:
            _LOGGER.debug("Telemetry payload is not JSON: %s", err)
            return {}

        snapshot = payload.get("data") or {}
        legends = snapshot.get("columnNamesByDeviceType") or {}
        records: dict[str, dict[str, Any]] = {}
        for row in snapshot.get("values") or []:
            if not isinstance(row, list) or not row:
                continue
            legend = legends.get(row[0])
            if not legend:
                continue
            record = dict(zip(legend, row, strict=False))
            device_id = record.get("DeviceId")
            if device_id:
                records[str(device_id)] = record
        _LOGGER.debug(
            "Account telemetry: %s record(s) for device types %s",
            len(records),
            sorted(legends)[:10],
        )
        return records

    @staticmethod
    def _match_telemetry_id(
        target_id: str, telemetry: dict[str, dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Return the telemetry record belonging to a discovered target id.

        The two sides spell a hardware id differently (the account reports
        ``Router-<24 hex characters>`` where discovery keeps the router's
        short id), so they are compared on the normalised hex tail.
        """
        wanted = re.sub(r"[^0-9a-z]", "", target_id.lower())
        if len(wanted) < 6:
            return None
        for device_id, record in telemetry.items():
            found = re.sub(r"[^0-9a-z]", "", device_id.lower())
            if found == wanted or found.endswith(wanted) or wanted.endswith(found):
                return record
        return None

    @staticmethod
    def _power_from_history(history: Any) -> dict[str, Any] | None:
        """Return the power series carried by a history message, if present.

        Newer firmware adds a repeated float field with one sample per second
        (900 values for the 15-minute window the app averages). The field number
        is not in the schema this integration ships, so the array is recognised
        by shape: an unknown length-delimited field of 600-1200 float32 values in
        a physically plausible range. Anything ambiguous is ignored.
        """
        try:
            raw = history.SerializeToString()
        except Exception:
            return None
        known = {field.number for field in history.DESCRIPTOR.fields}

        position = 0
        while position < len(raw):
            key, position = _read_varint(raw, position)
            number, wire = key >> 3, key & 7
            if wire == 0:
                _, position = _read_varint(raw, position)
                continue
            if wire == 1:
                position += 8
                continue
            if wire == 5:
                position += 4
                continue
            if wire != 2:
                return None
            length, position = _read_varint(raw, position)
            payload = raw[position : position + length]
            position += length
            if number in known or length % 4 or not POWER_SAMPLE_MIN <= length // 4 <= POWER_SAMPLE_MAX:
                continue
            values = struct.unpack(f"<{length // 4}f", payload)
            if not all(0.0 <= value <= POWER_VALUE_MAX for value in values):
                continue
            average = sum(values) / len(values)
            if not 1.0 <= average <= 300.0:
                continue
            return {
                "average_w": round(average, 1),
                "min_w": round(min(values), 1),
                "max_w": round(max(values), 1),
                "samples": len(values),
                "window_minutes": round(len(values) / 60, 1),
            }
        return None

    @staticmethod
    def energy_delta_wh(average_w: float, elapsed_s: float, window_s: float) -> float:
        """Return the energy used during ``elapsed_s`` at ``average_w``, in Wh.

        The series covers at most ``window_s`` seconds; a longer gap cannot be
        integrated from it. The elapsed part is used (never the whole window),
        so consecutive polls never count the same second twice.
        """
        if average_w <= 0 or elapsed_s <= 0:
            return 0.0
        covered = min(elapsed_s, window_s)
        return average_w * covered / 3600.0

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

        for target_id in list(self.discovered_ids):
            device_type = "dish" if target_id.startswith("ut") else "router"
            device_data: dict[str, Any] = {
                "status": {},
                "history": {},
                "type": device_type,
            }
            try:
                # 1. STATUS (POST is the gRPC-Web transport; the request kind
                # is a read and is checked in _grpc_web_frame)
                response = self._request(
                    "POST",
                    STARLINK_API_URL,
                    headers={
                        "origin": "https://www.starlink.com",
                        "referer": "https://www.starlink.com/account/home",
                        "content-type": "application/grpc-web+proto",
                        "x-grpc-web": "1",
                    },
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
                        device_data["status"]["state"] = _device_state(raw)
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
                            # answers "Unimplemented" or empty. A list is still
                            # accepted here so a firmware that starts reporting
                            # one is picked up; otherwise the client counts come
                            # from the account telemetry further down.
                            clients = raw.get("clients") or []
                            if clients:
                                device_data[DATA_WIFI_CLIENTS] = clients

                # 2. HISTORY
                response_history = self._request(
                    "POST",
                    STARLINK_API_URL,
                    headers={
                        "origin": "https://www.starlink.com",
                        "referer": "https://www.starlink.com/account/home",
                        "content-type": "application/grpc-web+proto",
                        "x-grpc-web": "1",
                    },
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
                        history_message = getattr(message_history, response_type_history)
                        device_data["history"] = MessageToDict(
                            history_message, preserving_proto_field_name=True
                        )
                        power = self._power_from_history(history_message)
                        if power is not None:
                            device_data["power"] = power
                            now = time.time()
                            if self._energy_last_ts:
                                delta = self.energy_delta_wh(
                                    power["average_w"],
                                    now - self._energy_last_ts,
                                    power["samples"],
                                )
                                self._energy_wh += delta
                            self._energy_last_ts = now
                            device_data["energy_kwh"] = round(self._energy_wh / 1000, 4)

                data[DATA_DEVICES][target_id] = device_data
                _LOGGER.debug("Poll succeeded for %s (%s)", target_id, device_type)
            except Exception as err:  # pylint: disable=broad-except
                # Per-poll transport failures are routine (a device can be
                # offline or the session stale): keep the log quiet and let the
                # entities show the gap, the user is warned once via the
                # repair issue instead.
                _LOGGER.debug("Poll failed for %s: %s", target_id, err)

        # Account-wide figures, both read from the account APIs: the Wi-Fi
        # client counts the routers report to the telemetry snapshot, and the
        # data usage of the current billing cycle. The snapshot is read first
        # because it is also a data-usage source.
        telemetry = self._cloud_telemetry()

        usage = self._account_data_usage(telemetry)
        if usage is not None:
            self._last_usage = usage
        if self._last_usage is not None:
            data[DATA_USAGE] = self._last_usage

        if telemetry:
            for target_id, device_data in data[DATA_DEVICES].items():
                if device_data.get("type") != "router":
                    continue
                if DATA_WIFI_CLIENTS in device_data:
                    continue
                record = self._match_telemetry_id(target_id, telemetry)
                if record is None:
                    continue
                alerts = record.get("ActiveAlerts")
                if alerts:
                    device_data["alerts"] = alerts
                device_data[DATA_WIFI_CLIENTS] = {
                    "count": _as_count(record.get("Clients")),
                    "count_2ghz": _as_count(record.get("Clients2Ghz")),
                    "count_5ghz": _as_count(record.get("Clients5Ghz")),
                    "count_ethernet": _as_count(record.get("ClientsEth")),
                    "wan_rx_bytes": _as_count(record.get("WanRxBytes")),
                    "wan_tx_bytes": _as_count(record.get("WanTxBytes")),
                    "bypassed": record.get("WifiIsBypassed"),
                    "hardware_version": record.get("WifiHardwareVersion"),
                    "software_version": record.get("WifiSoftwareVersion"),
                }

        return data

    async def async_send_command(
        self, target_id: str, request_field: str, request_data: Any
    ) -> bool:
        """Send the one allowed command (a restart) to a device."""
        return await self.hass.async_add_executor_job(
            self._send_command, target_id, request_field, request_data
        )

    def _send_command(
        self, target_id: str, request_field: str, request_data: Any
    ) -> bool:
        """Send a restart request (SyncWorker).

        Only ``reboot`` is accepted: the binding deliberately does not expose any
        other state-changing command.
        """
        if self._client is None:
            return False
        if request_field != "reboot":
            _LOGGER.warning("Refusing to send %s: only reboot is permitted", request_field)
            return False
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
        except Exception as err:
            _LOGGER.error("%s failed for %s: %s", request_field, target_id, err)
            return False

    @staticmethod
    def _grpc_web_frame(request: Any) -> bytes:
        """Wrap a read request in a gRPC-Web frame, refusing anything else."""
        kind = request.WhichOneof("request")
        if kind not in ALLOWED_GRPC_REQUESTS:
            raise ValueError(f"refusing to send a non-allowed Starlink request: {kind}")
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
