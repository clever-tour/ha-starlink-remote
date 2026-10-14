"""Constants for the Starlink Remote integration."""

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
