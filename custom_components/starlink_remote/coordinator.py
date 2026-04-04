"""DataUpdateCoordinator for Starlink Remote - Universal Discovery & Telemetry."""
from __future__ import annotations
import logging, time as _time, json, os, httpx, re, binascii
from datetime import timedelta
from typing import Any, Callable
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.components import persistent_notification
from .const import DOMAIN, CONF_COOKIE, CONF_SCAN_INTERVAL, DATA_DEVICES, DATA_WIFI_CLIENTS, DATA_USAGE, CONF_COOKIE_FILE

_LOGGER = logging.getLogger(__name__)
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

class StarlinkCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """
    Coordinator to handle session persistence, hardware discovery, and gRPC-Web polling.
    """

    def __init__(self, hass: HomeAssistant, entry: Any) -> None:
        """Initialize the coordinator."""
        self._entry = entry
        # Store persistent data in the standard .storage location
        self._persist_dir = hass.config.path('.storage', 'starlink-remote-cookie-storage')
        self._history_persist_path = os.path.join(self._persist_dir, 'history_persistence.json')
        self._cookie_persist_path = os.path.join(self._persist_dir, CONF_COOKIE_FILE)
        
        self.discovered_ids: set[str] = set()
        self._raw_cookie = ""
        self._xsrf_token = ""
        
        # Error tracking for 401 persistent notifications
        self._auth_failure_start: float | None = None
        self._notification_sent = False
        
        self._client: httpx.Client | None = None
        
        super().__init__(
            hass, _LOGGER, name=DOMAIN, 
            update_interval=timedelta(seconds=entry.data.get(CONF_SCAN_INTERVAL, 60))
        )

    async def _async_setup(self):
        """Perform initial data loading and session priming."""
        await self.hass.async_add_executor_job(self._init_client_and_load_data)
        await self.hass.async_add_executor_job(self._refresh_session)
        await self.hass.async_add_executor_job(self._discover_hardware)

    def _init_client_and_load_data(self):
        """Initialize the persistent client and load data from disk (SyncWorker)."""
        if self._client is None:
            self._client = httpx.Client(http2=True, timeout=15.0, follow_redirects=True)
        
        self._load_persistent_data()
        
        cookie_file_dev = os.path.join(os.path.dirname(__file__), 'cookie.txt')
        
        if os.path.exists(self._cookie_persist_path):
            try:
                with open(self._cookie_persist_path, 'r') as f:
                    self._raw_cookie = f.read().strip()
            except Exception as e:
                _LOGGER.error("Failed to read persistent cookie: %s", e)
        elif os.path.exists(cookie_file_dev):
            try:
                with open(cookie_file_dev, 'r') as f:
                    self._raw_cookie = f.read().strip()
            except Exception as e:
                _LOGGER.error("Failed to read dev cookie.txt: %s", e)
        
        if not self._raw_cookie:
            self._raw_cookie = self._entry.data.get(CONF_COOKIE, "")

        self._sync_cookies_to_client()

    def _sync_cookies_to_client(self):
        """Inject the raw cookie string into the httpx.Client jar."""
        if not self._raw_cookie or not self._client: return
        for part in self._raw_cookie.split(';'):
            if '=' in part:
                k, v = part.strip().split('=', 1)
                self._client.cookies.set(k, v, domain='.starlink.com')
        
        self._xsrf_token = self._client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')
        if not self._xsrf_token:
            match = re.search(r'XSRF-TOKEN=([^;]+)', self._raw_cookie)
            if match: self._xsrf_token = match.group(1)

    def _load_persistent_data(self):
        """Restore discovered hardware IDs from disk."""
        try:
            os.makedirs(self._persist_dir, exist_ok=True)
            if os.path.exists(self._history_persist_path):
                with open(self._history_persist_path, 'r') as f:
                    h = json.load(f)
                    for tid in h.get('discovered_ids', []):
                        self.discovered_ids.add(tid)
        except Exception: pass

    def _save_persistent_data(self):
        """Persist discovered hardware IDs and current cookie to disk."""
        try:
            os.makedirs(self._persist_dir, exist_ok=True)
            with open(self._history_persist_path, 'w') as f:
                json.dump({'discovered_ids': list(self.discovered_ids)}, f)
            
            if self._raw_cookie:
                with open(self._cookie_persist_path, 'w') as f:
                    f.write(self._raw_cookie)
        except Exception as e:
            _LOGGER.error("Save failed: %s", e)

    def _refresh_session(self) -> bool:
        """Execute the session priming cycle."""
        if not self._client: return False
        try:
            headers = {"User-Agent": UA, "cookie": self._raw_cookie, "x-xsrf-token": self._xsrf_token}
            r1 = self._client.get('https://www.starlink.com/account/home', headers=headers)
            r2 = self._client.get('https://api.starlink.com/auth-rp/auth/user', headers=headers)
            
            if r1.status_code == 401 or r2.status_code == 401:
                self._handle_auth_failure()
                return False
            
            self._handle_auth_success()
            
            new_jar = "; ".join([f"{c.name}={c.value}" for c in self._client.cookies.jar])
            if new_jar:
                self._raw_cookie = new_jar
                self._xsrf_token = self._client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default=self._xsrf_token)
                self._save_persistent_data()
            _LOGGER.warning("[SESSION] Refreshed successfully.")
            return True
        except Exception:
            return False

    def _handle_auth_failure(self):
        """Track consecutive auth failures and notify user if threshold exceeded."""
        now = _time.time()
        if self._auth_failure_start is None:
            self._auth_failure_start = now
        
        if not self._notification_sent and (now - self._auth_failure_start >= 60):
            _LOGGER.warning("Persistent 401 detected. Sending notification.")
            persistent_notification.create(
                self.hass,
                "Starlink session has expired. Please re-enter your browser cookie in the integration settings to restore telemetry.",
                title="Starlink Remote Authentication Error",
                notification_id="starlink_remote_auth_error"
            )
            self._notification_sent = True
            self.hass.add_job(
                self.hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": "reauth"}, data=self._entry.data
                )
            )

    def _handle_auth_success(self):
        """Reset auth failure tracking on success."""
        if self._auth_failure_start is not None:
            self._auth_failure_start = None
            if self._notification_sent:
                persistent_notification.dismiss(self.hass, "starlink_remote_auth_error")
                self._notification_sent = False

    def _discover_hardware(self):
        """Dynamically identify Dishes and Routers."""
        if not self._client: return
        headers = {"User-Agent": UA, "cookie": self._raw_cookie, "x-xsrf-token": self._xsrf_token}
        try:
            r = self._client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=headers)
            if r.status_code == 200:
                data = r.json()
                for res in data.get("content", {}).get("results", []):
                    for ut in res.get("userTerminals", []):
                        uid = ut.get("userTerminalId")
                        if uid: self.discovered_ids.add(f"ut{uid}")
                        for rtr in ut.get("routers", []):
                            rid = rtr.get("routerId")
                            if rid: self.discovered_ids.add(f"Router-{rid}")
        except Exception: pass

        try:
            r = self._client.get("https://www.starlink.com/account/home", headers=headers)
            if r.status_code == 200:
                found = set(re.findall(r"Router-[A-Fa-f0-9]{24}", r.text))
                found.update(re.findall(r"ut[a-f0-9-]{36}", r.text))
                found.update(re.findall(r'selectedDevice=([A-Fa-f0-9-]+)', r.text))
                self.discovered_ids.update(found)
        except Exception: pass

        if self.discovered_ids:
            self._save_persistent_data()

    async def _async_update_data(self) -> dict[str, Any]:
        """Perform the periodic update cycle."""
        await self.hass.async_add_executor_job(self._refresh_session)
        if not self.discovered_ids:
            await self.hass.async_add_executor_job(self._discover_hardware)
        return await self.hass.async_add_executor_job(self._fetch_all)

    def _fetch_all(self) -> dict[str, Any]:
        """Poll telemetry using gRPC-Web binary tunneling."""
        if not self._client: return {DATA_DEVICES: {}}
        from .spacex.api.device.device_pb2 import Request, GetStatusRequest, GetHistoryRequest, Response
        from google.protobuf.json_format import MessageToDict
        
        data = {DATA_DEVICES: {}}
        all_clients = []
        headers = {
            "User-Agent": UA, "cookie": self._raw_cookie, "x-xsrf-token": self._xsrf_token,
            "origin": "https://www.starlink.com", "referer": "https://www.starlink.com/account/home",
            "content-type": "application/grpc-web+proto", "x-grpc-web": "1"
        }
        url = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"

        for tid in list(self.discovered_ids):
            dev_type = 'dish' if tid.startswith('ut') else 'router'
            dev_data = {'status': {}, 'history': {}, 'type': dev_type, DATA_WIFI_CLIENTS: []}
            try:
                # 1. STATUS
                req = Request(target_id=tid, get_status=GetStatusRequest())
                ser = req.SerializeToString()
                frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
                res = self._client.post(url, headers=headers, content=frame)
                
                if res.status_code == 401:
                    self._handle_auth_failure()
                
                if res.status_code == 200 and len(res.content) > 5:
                    self._handle_auth_success()
                    msg_len = int.from_bytes(res.content[1:5], 'big')
                    out = Response()
                    out.ParseFromString(res.content[5:5+msg_len])
                    rt = out.WhichOneof('response')
                    if rt:
                        rd = MessageToDict(getattr(out, rt), preserving_proto_field_name=True)
                        dev_data['status'] = rd
                        dev_data['status']['state'] = 'CONNECTED'
                        if rt == 'wifi_get_status':
                            clients = rd.get('clients', [])
                            dev_data[DATA_WIFI_CLIENTS] = clients
                            all_clients.extend(clients)

                # 2. HISTORY
                req_h = Request(target_id=tid, get_history=GetHistoryRequest())
                ser_h = req_h.SerializeToString()
                frame_h = b'\x00' + len(ser_h).to_bytes(4, 'big') + ser_h
                res_h = self._client.post(url, headers=headers, content=frame_h)
                
                if res_h.status_code == 200 and len(res_h.content) > 5:
                    msg_len_h = int.from_bytes(res_h.content[1:5], 'big')
                    out_h = Response()
                    out_h.ParseFromString(res_h.content[5:5+msg_len_h])
                    rt_h = out_h.WhichOneof('response')
                    if rt_h:
                        dev_data['history'] = MessageToDict(getattr(out_h, rt_h), preserving_proto_field_name=True)
                
                data[DATA_DEVICES][tid] = dev_data
                _LOGGER.warning("[POLL] Success for %s (%s)", tid, dev_type)
            except Exception as e:
                _LOGGER.error("[POLL] Error for %s: %s", tid, e)
        
        data[DATA_WIFI_CLIENTS] = all_clients
        raw_bytes = sum(float(c.get('rx_stats', {}).get('bytes', 0)) for c in all_clients)
        data[DATA_USAGE] = {'total_gb': round(raw_bytes / (1024**3), 3)}
        
        return data
