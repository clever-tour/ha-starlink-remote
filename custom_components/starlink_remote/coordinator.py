"""DataUpdateCoordinator for Starlink Remote - Universal Discovery & Telemetry."""
from __future__ import annotations
import logging, time as _time, json, os, httpx, re, binascii
from datetime import timedelta
from typing import Any, Callable
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import DOMAIN, CONF_COOKIE, CONF_SCAN_INTERVAL, DATA_DEVICES, DATA_WIFI_CLIENTS, DATA_USAGE

_LOGGER = logging.getLogger(__name__)
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

class StarlinkCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: Any) -> None:
        self._entry = entry
        self._persist_dir = hass.config.path('.starlink_cookies')
        self._history_persist_path = os.path.join(self._persist_dir, 'history_persistence.json')
        self.discovered_ids: set[str] = set()
        self._raw_cookie = ""
        self._xsrf_token = ""
        
        # Persistent client for automatic cookie management across subdomains
        self._client = httpx.Client(http2=True, timeout=15.0, follow_redirects=True)
        
        super().__init__(
            hass, _LOGGER, name=DOMAIN, 
            update_interval=timedelta(seconds=entry.data.get(CONF_SCAN_INTERVAL, 60))
        )

    async def _async_setup(self):
        await self.hass.async_add_executor_job(self._load_persistent_data)
        
        # Priority 1: cookie.txt (Dev)
        # Priority 2: config_entry
        cookie_file = os.path.join(os.path.dirname(__file__), 'cookie.txt')
        if os.path.exists(cookie_file):
            with open(cookie_file, 'r') as f:
                self._raw_cookie = f.read().strip()
        else:
            self._raw_cookie = self._entry.data.get(CONF_COOKIE, "")

        self._sync_cookies_to_client()
        
        # Initial discovery
        await self.hass.async_add_executor_job(self._refresh_session)
        await self.hass.async_add_executor_job(self._discover_hardware)

    def _sync_cookies_to_client(self):
        """Parse raw cookie string into the client's internal jar."""
        if not self._raw_cookie: return
        for part in self._raw_cookie.split(';'):
            if '=' in part:
                k, v = part.strip().split('=', 1)
                self._client.cookies.set(k, v, domain='.starlink.com')
        
        self._xsrf_token = self._client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')
        if not self._xsrf_token:
            match = re.search(r'XSRF-TOKEN=([^;]+)', self._raw_cookie)
            if match: self._xsrf_token = match.group(1)

    def _load_persistent_data(self):
        try:
            if os.path.exists(self._history_persist_path):
                h = json.load(open(self._history_persist_path, 'r'))
                for tid in h.get('discovered_ids', []):
                    self.discovered_ids.add(tid)
        except: pass

    def _save_persistent_data(self):
        try:
            os.makedirs(self._persist_dir, exist_ok=True)
            json.dump({
                'discovered_ids': list(self.discovered_ids)
            }, open(self._history_persist_path, 'w'))
        except: pass

    def _refresh_session(self) -> bool:
        """Keep the session alive by hitting the main account page and API priming endpoint."""
        try:
            headers = {"User-Agent": UA, "cookie": self._raw_cookie, "x-xsrf-token": self._xsrf_token}
            
            # 1. Main site SSO persistence
            r1 = self._client.get('https://www.starlink.com/account/home', headers=headers)
            
            # 2. API Priming (Access.V1 token sync)
            r2 = self._client.get('https://api.starlink.com/auth-rp/auth/user', headers=headers)
            
            # Sync fresh cookies back
            new_jar = "; ".join([f"{c.name}={c.value}" for c in self._client.cookies.jar])
            if new_jar:
                self._raw_cookie = new_jar
                self._xsrf_token = self._client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default=self._xsrf_token)
            
            _LOGGER.debug("[SESSION] Refreshed. HTTP Status: %d, %d", r1.status_code, r2.status_code)
            return r1.status_code == 200 or r2.status_code == 200
        except Exception as e:
            _LOGGER.debug("[SESSION] Refresh failed: %s", e)
            return False

    def _discover_hardware(self):
        """Identify hardware IDs using the service-lines API and dashboard crawl."""
        headers = {
            "User-Agent": UA, "cookie": self._raw_cookie, "x-xsrf-token": self._xsrf_token,
            "origin": "https://www.starlink.com", "referer": "https://www.starlink.com/account/home"
        }
        
        # 1. Official Webagg API
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
        except: pass

        # 2. HTML Crawl (Fallback for selectedDevice= patterns)
        try:
            r = self._client.get("https://www.starlink.com/account/home", headers=headers)
            if r.status_code == 200:
                found = set(re.findall(r"Router-[A-Fa-f0-9]{24}", r.text))
                found.update(re.findall(r"ut[a-f0-9-]{36}", r.text))
                found.update(re.findall(r'selectedDevice=([A-Fa-f0-9-]+)', r.text))
                self.discovered_ids.update(found)
        except: pass

        if self.discovered_ids:
            _LOGGER.warning("[DISCOVERY] Active Hardware: %s", self.discovered_ids)
            self._save_persistent_data()

    async def _async_update_data(self) -> dict[str, Any]:
        """Update cycle: Refresh session, Discover if needed, Fetch Telemetry."""
        try:
            # Refresh on every cycle as requested
            await self.hass.async_add_executor_job(self._refresh_session)
            
            # Re-discover if we have no hardware yet
            if not self.discovered_ids:
                await self.hass.async_add_executor_job(self._discover_hardware)
            
            return await self.hass.async_add_executor_job(self._fetch_all)
        except Exception as exc:
            _LOGGER.warning("Update failed: %s", exc)
            return self.data if self.data else {}

    def _fetch_all(self) -> dict[str, Any]:
        """Poll telemetry for all identified devices via gRPC-Web tunnel."""
        from .spacex.api.device.device_pb2 import Request, GetStatusRequest, Response
        from google.protobuf.json_format import MessageToDict
        
        data = {DATA_DEVICES: {}}
        all_clients = []
        
        headers = {
            "User-Agent": UA, "cookie": self._raw_cookie, "x-xsrf-token": self._xsrf_token,
            "origin": "https://www.starlink.com", "referer": "https://www.starlink.com/account/home",
            "content-type": "application/grpc-web+proto", "x-grpc-web": "1", "accept": "*/*"
        }
        url = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"

        for tid in list(self.discovered_ids):
            dev_data = {'status': {}, DATA_WIFI_CLIENTS: []}
            try:
                # Binary framing for gRPC-Web
                req = Request(target_id=tid, get_status=GetStatusRequest())
                ser = req.SerializeToString()
                frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
                
                res = self._client.post(url, headers=headers, content=frame)
                
                if res.status_code == 200 and len(res.content) > 5:
                    msg_len = int.from_bytes(res.content[1:5], 'big')
                    out = Response()
                    out.ParseFromString(res.content[5:5+msg_len])
                    rt = out.WhichOneof('response')
                    if rt:
                        rd = MessageToDict(getattr(out, rt), preserving_proto_field_name=True)
                        dev_data['status'] = rd
                        dev_data['status']['state'] = 'CONNECTED'
                        
                        # WiFi clients aggregation
                        if rt == 'wifi_get_status':
                            clients = rd.get('clients', [])
                            dev_data[DATA_WIFI_CLIENTS] = clients
                            all_clients.extend(clients)
                    
                    data[DATA_DEVICES][tid] = dev_data
                else:
                    _LOGGER.warning("[POLL] HTTP %d for %s (Len: %d)", res.status_code, tid, len(res.content))
            except Exception as e:
                _LOGGER.error("[POLL] Error for %s: %s", tid, e)
                continue
        
        # Aggregations
        data[DATA_WIFI_CLIENTS] = all_clients
        raw_bytes = sum(float(c.get('rx_stats', {}).get('bytes', 0)) for c in all_clients)
        data[DATA_USAGE] = {'total_gb': round(raw_bytes / (1024**3), 3)}
        
        return data
