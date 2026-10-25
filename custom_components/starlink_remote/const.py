"""Constants for the Starlink Remote integration."""

import os
from urllib.parse import urlsplit, urlunsplit

DOMAIN = "starlink_remote"

#: Name of the integration, also used as the base of every config entry title.
DEFAULT_TITLE = "Starlink Remote"

# --- Config entry / options keys -------------------------------------------------
CONF_COOKIE = "cookie"
CONF_NAME = "name"
CONF_COOKIE_DIR = "cookie_dir"
CONF_SCAN_INTERVAL = "scan_interval"

#: Poll interval in seconds when the entry does not override it.
DEFAULT_SCAN_INTERVAL = 60

#: Directory below ``<config>/.storage`` that holds the session material and
#: the discovered-hardware metrics (see ``storage.py``). The name is unchanged
#: so an existing installation keeps using the cookie it already stored.
STORAGE_DIR = "starlink-remote-cookie-storage"
CONF_COOKIE_FILE = "cookie.txt"

#: Repair issue raised when the stored session stops being accepted. It is
#: fixable, so Home Assistant offers the cookie repair flow for it.
ISSUE_SESSION_EXPIRED = "session_expired"

# --- Data keys inside ``StarlinkCoordinator.data`` -------------------------------
#: ``{target_id: {"status": {...}, "history": {...}, "type": "dish"|"router"|...}}``
DATA_DEVICES = "devices"
DATA_WIFI_CLIENTS = "wifi_clients"
DATA_USAGE = "data_usage"
# --- HTTP identity ---------------------------------------------------------------
#: User-Agent for every starlink.com request. Shared by the coordinator and the
#: cookie validation in the config flows: the account API answers differently to
#: a non-browser agent.
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)

# --- Endpoints -------------------------------------------------------------------
#: Account API: hardware discovery (service lines, terminals, routers).
#: The account-wide data usage figure is not part of it; that comes from
#: STARLINK_TELEMETRYAGG_DATA_USAGE.
STARLINK_WEB_SERVICE_LINES = "https://api.starlink.com/webagg/v2/accounts/service-lines"

#: Account-wide data usage for one service line, one entry per billing cycle.
#: The service-lines payload does not carry this figure (its terminals report
#: their own counters); this is what the Starlink app shows under "Data usage".
#: Filled with the account reference id and the service line number.
STARLINK_TELEMETRYAGG_DATA_USAGE = (
    "https://api.starlink.com/telemetryagg/v1/data-usage/account/{account}"
    "/service-line/{service_line}/annotated"
)

#: Per-device telemetry snapshot of one account. Routers report their Wi-Fi
#: client counts here; the per-device gRPC polls expose no client list on
#: api_version 129.
STARLINK_DEVICE_TELEMETRY = (
    "https://api.starlink.com/device-data/cache/v1/telemetry"
)
#: gRPC-Web endpoint for device telemetry. Must stay on the ``www.`` host: an
#: api. host redirect would turn the POSTs into redirects, which break the
#: binary gRPC-Web framing.
STARLINK_API_URL = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"
#: Session probe: the cookie is considered live while this does not answer 401.
STARLINK_AUTH_URL = "https://api.starlink.com/auth-rp/auth/user"
#: Data-usage sources, in the order the coordinator tries them. The first one
#: is the annotated aggregate the integration has always used; the others are
#: fallbacks for accounts where it answers with nothing usable.
USAGE_SOURCE_ANNOTATED = "annotated"
USAGE_SOURCE_TELEMETRY = "telemetry_bytes"
USAGE_SOURCE_EXPORT = "data_block_export"

#: Data-block export (CSV). Carries per-block capacity and, on accounts that
#: use data blocks, the consumed amount; used only as a fallback parser.
STARLINK_DATA_USAGE_EXPORT = (
    "https://starlink.com/api/webagg/v1/public/data-usage/export?accountNumber={account}"
)

#: Mints a short-lived bearer token from a live SSO cookie. The browser access
#: cookies expire long before the session does; this is how the web app keeps
#: working, and the same token is accepted by the REST APIs and gRPC-Web.
STARLINK_TOKEN_REFRESH = "https://starlink.com/api/auth/auth/refresh-token"

#: Portal page the session is primed against and scraped for hardware ids.
STARLINK_PORTAL_HOME = "https://www.starlink.com/account/home"

# --- Development override --------------------------------------------------------
#: When set, every endpoint above is redirected to this base URL - scheme, host and
#: port are replaced, the path is kept. It exists so the integration can be run
#: against the local stand-in in ``devtools/starlink_mock`` (see DEVELOPMENT.md).
#: Unset in every normal installation, where the constants above are used verbatim.
DEV_BASE_URL = os.environ.get("STARLINK_REMOTE_DEV_BASE_URL", "").rstrip("/")


def _dev_url(url: str) -> str:
    """Return ``url`` pointed at the development base, path unchanged."""
    if not DEV_BASE_URL:
        return url
    base = urlsplit(DEV_BASE_URL)
    original = urlsplit(url)
    return urlunsplit((base.scheme, base.netloc, original.path, original.query, ""))


if DEV_BASE_URL:  # pragma: no cover - only ever active in a development setup
    STARLINK_WEB_SERVICE_LINES = _dev_url(STARLINK_WEB_SERVICE_LINES)
    STARLINK_TELEMETRYAGG_DATA_USAGE = _dev_url(STARLINK_TELEMETRYAGG_DATA_USAGE)
    STARLINK_DEVICE_TELEMETRY = _dev_url(STARLINK_DEVICE_TELEMETRY)
    STARLINK_API_URL = _dev_url(STARLINK_API_URL)
    STARLINK_AUTH_URL = _dev_url(STARLINK_AUTH_URL)
    STARLINK_PORTAL_HOME = _dev_url(STARLINK_PORTAL_HOME)
    STARLINK_DATA_USAGE_EXPORT = _dev_url(STARLINK_DATA_USAGE_EXPORT)
    STARLINK_TOKEN_REFRESH = _dev_url(STARLINK_TOKEN_REFRESH)
