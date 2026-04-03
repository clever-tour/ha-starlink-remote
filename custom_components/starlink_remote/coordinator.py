"""DataUpdateCoordinator for Starlink Remote."""
from __future__ import annotations
import logging, time as _time, json, os, httpx, re
from datetime import timedelta
from typing import Any, Callable
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import (
    DOMAIN, CONF_COOKIE, CONF_ROUTER_ID, CONF_SCAN_INTERVAL,
    DATA_DISH_STATUS, DATA_DISH_HISTORY, DATA_WIFI_CLIENTS, 
    DATA_USAGE, STARLINK_AUTH_URL
)
_LOGGER = logging.getLogger(__name__)
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

class StarlinkCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: Any) -> None:
        self._entry = entry
        self._router_id = entry.data[CONF_ROUTER_ID].strip()
        if not self._router_id.startswith('Router-'):
            self._router_id = f'Router-{self._router_id}'
            
        self._outage_history = {}; self._wifi_events = []; self._last_clients = set()
        self._persist_dir = hass.config.path('.starlink_cookies')
        self._session_path = os.path.join(self._persist_dir, 'session.json')
        self._history_persist_path = os.path.join(self._persist_dir, 'history_persistence.json')
        self._cookie_file = os.path.join(os.path.dirname(__file__), 'cookie.txt')
        self._cookie_jar = httpx.Cookies()
        self._dish_id = None
        self._ids = [self._router_id]
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=entry.data.get(CONF_SCAN_INTERVAL, 60)))

    async def _async_setup(self):
        await self.hass.async_add_executor_job(self._load_persistent_data)
        if self._dish_id and self._dish_id not in self._ids:
            self._ids.append(self._dish_id)
        
        if not self._cookie_jar:
            nc = await self.hass.async_add_executor_job(self._read_cookie_file)
            if nc: self._load_cookies_from_str(nc)
            else: self._load_cookies_from_str(self._entry.data[CONF_COOKIE])
        
        self._client = httpx.Client(http2=True, cookies=self._cookie_jar, timeout=15.0, follow_redirects=True)
        await self.hass.async_add_executor_job(self._refresh_session)

    def _read_cookie_file(self):
        try: return open(self._cookie_file, 'r').read().strip()
        except: return ''

    def _load_cookies_from_str(self, cookie_str: str):
        if not cookie_str: return
        for part in cookie_str.split(';'):
            if '=' in part:
                k, v = part.strip().split('=', 1)
                self._cookie_jar.set(k, v, domain='.starlink.com')

    def _load_persistent_data(self):
        try:
            if os.path.exists(self._session_path):
                s = json.load(open(self._session_path, 'r'))
                for c in s.get('cookies', []):
                    self._cookie_jar.set(c['name'], c['value'], domain=c.get('domain'), path=c.get('path'))
            if os.path.exists(self._history_persist_path):
                h = json.load(open(self._history_persist_path, 'r'))
                self._outage_history = h.get('outages', {})
                self._wifi_events = h.get('wifi_events', [])
                self._dish_id = h.get('dish_id')
        except: pass

    def _save_persistent_data(self):
        try:
            os.makedirs(self._persist_dir, exist_ok=True)
            if self._client:
                cl = [{'name': c.name, 'value': c.value, 'domain': c.domain, 'path': c.path} for c in self._client.cookies.jar]
                json.dump({'cookies': cl}, open(self._session_path, 'w'))
            json.dump({'outages': self._outage_history, 'wifi_events': self._wifi_events[-100:], 'dish_id': self._dish_id}, open(self._history_persist_path, 'w'))
        except: pass

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.hass.async_add_executor_job(self._fetch_all)
            cur_c = {c.get('mac_address'): c.get('name') or c.get('ip_address') or c.get('mac_address') for c in data.get(DATA_WIFI_CLIENTS, []) if c.get('mac_address')}
            cur_m = set(cur_c.keys())
            if self._last_clients:
                for m in (cur_m - self._last_clients):
                    self._wifi_events.append({'t': _time.time(), 'event': 'JOINED', 'device': cur_c.get(m)})
                for m in (self._last_clients - cur_m):
                    self._wifi_events.append({'t': _time.time(), 'event': 'LEFT', 'mac': m})
            self._last_clients = cur_m
            
            cls = data.get(DATA_WIFI_CLIENTS, [])
            raw = sum(float(c.get('rx_stats', {}).get('bytes', 0)) + float(c.get('rxStats', {}).get('bytes', 0)) for c in cls)
            data[DATA_USAGE] = {'total_gb': round(raw / (1024**3), 3), 'wifi_event_log': sorted(self._wifi_events, key=lambda x: x['t'], reverse=True)[:50]}
            
            await self.hass.async_add_executor_job(self._save_persistent_data)
            return data
        except Exception as exc:
            _LOGGER.warning("Poll failed: %s", exc)
            return self.data if self.data else {}

    def _fetch_all(self) -> dict[str, Any]:
        from .spacex.api.device.device_pb2 import Request, GetStatusRequest, GetHistoryRequest, Response
        from google.protobuf.json_format import MessageToDict
        
        def _make_call(tid, req_obj):
            ser = req_obj.SerializeToString()
            frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
            cookie_str = "; ".join([f"{c.name}={c.value}" for c in self._client.cookies.jar])
            headers = {
                'accept': '*/*', 'content-type': 'application/grpc-web+proto', 'x-grpc-web': '1', 
                'user-agent': UA, 'cookie': cookie_str, 'origin': 'https://starlink.com'
            }
            url = 'https://starlink.com/api/SpaceX.API.Device.Device/Handle'
            res = self._client.post(url, headers=headers, content=frame)
            if res.status_code == 401: self._refresh_session()
            if len(res.content) < 5: return Response()
            out = Response()
            out.ParseFromString(res.content[5:5+int.from_bytes(res.content[1:5], 'big')])
            return out
        
        data = {DATA_DISH_STATUS: {}, DATA_DISH_HISTORY: {}, DATA_WIFI_CLIENTS: []}
        for tid in self._ids:
            try:
                resp = _make_call(tid, Request(target_id=tid, get_status=GetStatusRequest()))
                rt = resp.WhichOneof('response')
                if rt:
                    rd = MessageToDict(getattr(resp, rt), preserving_proto_field_name=True)
                    if rt == 'wifi_get_status':
                        data[DATA_WIFI_CLIENTS].extend(rd.get('clients', []))
                        if not data[DATA_DISH_STATUS]:
                             d = data[DATA_DISH_STATUS]; d['state'] = 'CONNECTED'
                             for k, v in rd.items(): d[k] = v
                        if 'dish_id' in rd and rd['dish_id'] not in self._ids:
                            self._dish_id = rd['dish_id']
                            self._ids.append(rd['dish_id'])
                        if 'dish_get_status' in rd:
                            ds = rd['dish_get_status']
                            for k, v in ds.items(): data[DATA_DISH_STATUS][k] = v
                    elif rt == 'dish_get_status':
                        data[DATA_DISH_STATUS].update(rd)
            except: continue
            
            try:
                resp_h = _make_call(tid, Request(target_id=tid, get_history=GetHistoryRequest()))
                ht = resp_h.WhichOneof('response')
                if ht:
                    h = MessageToDict(getattr(resp_h, ht), preserving_proto_field_name=True)
                    if 'history' in h: h = h['history']
                    l = [s for s in h.get('pop_ping_latency_ms', []) if s is not None]
                    if l: 
                        l.sort()
                        data[DATA_DISH_HISTORY]['avg_latency_ms'] = sum(l)/len(l)
                        data[DATA_DISH_HISTORY]['p95_latency_ms'] = l[int(len(l)*0.95)]
                    for o in h.get('outages', []):
                        ts = o.get('start_timestamp_ns')
                        if ts: self._outage_history[str(ts)] = o
                    max_ts = max([int(k) for k in self._outage_history.keys()] + [0])
                    cutoff = max_ts - (24 * 3600 * 10**9)
                    self._outage_history = {k: v for k, v in self._outage_history.items() if int(k) > cutoff}
                    dh = data[DATA_DISH_HISTORY]
                    dh['outage_count_24h'] = len(self._outage_history)
                    dh['outage_list_24h'] = sorted(self._outage_history.values(), key=lambda x: int(x.get('start_timestamp_ns', 0)), reverse=True)
                    dh['searching_count_24h'] = sum(1 for o in self._outage_history.values() if 'SEARCH' in (o.get('cause') or '').upper())
                    dh['booting_count_24h'] = sum(1 for o in self._outage_history.values() if any(k in (o.get('cause') or '').upper() for k in ['BOOT','REBOOT','NO_PINGS']))
            except: continue
        return data

    def _refresh_session(self) -> bool:
        try:
            r = self._client.get('https://api.starlink.com/auth-rp/auth/user', headers={'user-agent': UA})
            return r.status_code == 200
        except: return False
