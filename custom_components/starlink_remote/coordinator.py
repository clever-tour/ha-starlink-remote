"""DataUpdateCoordinator for Starlink Remote - Verified High Fidelity Version."""
from __future__ import annotations
import logging, time as _time, json, os, httpx, re, binascii
from datetime import timedelta
from typing import Any
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
        self.discovered_ids: set[str] = {"Router-0100000000000000008B65AD", "ut10588f9d-45017219-5815f472"}
        self._raw_cookie = ""
        self._xsrf_token = ""
        
        super().__init__(
            hass, _LOGGER, name=DOMAIN, 
            update_interval=timedelta(seconds=entry.data.get(CONF_SCAN_INTERVAL, 60))
        )

    async def _async_setup(self):
        await self.hass.async_add_executor_job(self._load_persistent_data)
        
        # Priority 1: cookie.txt file (for developer testing)
        # Priority 2: config_entry data
        cookie_file = os.path.join(os.path.dirname(__file__), 'cookie.txt')
        if os.path.exists(cookie_file):
            with open(cookie_file, 'r') as f:
                self._raw_cookie = f.read().strip()
        else:
            self._raw_cookie = self._entry.data.get(CONF_COOKIE, "")
        
        # Extract XSRF for header injection
        match = re.search(r'XSRF-TOKEN=([^;]+)', self._raw_cookie)
        if match:
            self._xsrf_token = match.group(1)

        await self.hass.async_add_executor_job(self._discover_hardware)

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

    def _discover_hardware(self):
        headers = {
            "User-Agent": UA, "cookie": self._raw_cookie, "x-xsrf-token": self._xsrf_token,
            "origin": "https://www.starlink.com", "referer": "https://www.starlink.com/account/home"
        }
        try:
            with httpx.Client(http2=True, timeout=10.0) as client:
                r = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=headers)
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
        _LOGGER.info("[DISCOVERY] Active IDs: %s", self.discovered_ids)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.hass.async_add_executor_job(self._fetch_all)
        except Exception as exc:
            _LOGGER.warning("Update failed: %s", exc)
            return self.data if self.data else {}

    def _fetch_all(self) -> dict[str, Any]:
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

        with httpx.Client(http2=True, timeout=15.0) as client:
            for tid in self.discovered_ids:
                dev_data = {'status': {}, DATA_WIFI_CLIENTS: []}
                try:
                    req = Request(target_id=tid, get_status=GetStatusRequest())
                    ser = req.SerializeToString()
                    frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
                    
                    res = client.post(url, headers=headers, content=frame)
                    
                    if len(res.content) > 5:
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
                    
                    data[DATA_DEVICES][tid] = dev_data
                except Exception as e:
                    _LOGGER.error("Poll failed for %s: %s", tid, e)
                    continue
        
        # Aggregations
        data[DATA_WIFI_CLIENTS] = all_clients
        raw_bytes = sum(float(c.get('rx_stats', {}).get('bytes', 0)) for c in all_clients)
        data[DATA_USAGE] = {'total_gb': round(raw_bytes / (1024**3), 3)}
        
        self._save_persistent_data()
        return data
