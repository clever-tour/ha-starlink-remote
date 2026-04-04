DOMAIN = 'starlink_remote'
CONF_COOKIE = 'cookie'
CONF_SCAN_INTERVAL = 'scan_interval'
CONF_NAME = 'name'
CONF_COOKIE_DIR = 'cookie_dir'
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_COOKIE_DIR = '/config/.storage/starlink-remote-cookie-storage'
CONF_COOKIE_FILE = 'cookie.txt'

# Data keys in coordinator.data
DATA_DEVICES = 'devices'  # Will be a dict: { target_id: { status: {}, history: {}, ... } }
DATA_WIFI_CLIENTS = 'wifi_clients'
DATA_USAGE = 'data_usage'

STARLINK_WEB_SERVICE_LINES = 'https://api.starlink.com/webagg/v2/accounts/service-lines'
STARLINK_API_URL = 'https://starlink.com/api/SpaceX.API.Device.Device/Handle'
STARLINK_AUTH_URL = 'https://api.starlink.com/auth-rp/auth/user'
