from __future__ import annotations
import logging
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from .const import CONF_COOKIE, CONF_ROUTER_ID, CONF_NAME, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DEFAULT_COOKIE_DIR, DOMAIN, STARLINK_WEB_SERVICE_LINES
_LOGGER = logging.getLogger(__name__)
class StarlinkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    def __init__(self) -> None:
        self._cookie: str | None = None
        self._discovered_devices: list[dict[str, str]] = []
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            self._cookie = user_input[CONF_COOKIE]
            try:
                self._discovered_devices = await self.hass.async_add_executor_job(self._discover_devices, self._cookie)
                if not self._discovered_devices: errors['base'] = 'no_devices_found'
                else: return await self.async_step_select_device()
            except Exception: errors['base'] = 'invalid_auth'
        return self.async_show_form(step_id='user', data_schema=vol.Schema({vol.Required(CONF_COOKIE): str}), errors=errors)
    def _discover_devices(self, cookie: str) -> list[dict[str, str]]:
        import httpx
        headers = {'accept': 'application/json', 'cookie': cookie, 'user-agent': 'Mozilla/5.0'}
        with httpx.Client() as client:
            resp = client.get(STARLINK_WEB_SERVICE_LINES, headers=headers, timeout=10.0)
            data = resp.json()
            found = []
            for res in data.get('content', {}).get('results', []):
                nickname = res.get('nickname', 'Dish')
                for ut in res.get('userTerminals', []):
                    routers = ut.get('routers', [])
                    if routers:
                        for r in routers: found.append({'id': r.get('routerId'), 'name': f"{nickname} (Router)"})
                    else:
                        found.append({'id': ut.get('userTerminalId'), 'name': f"{nickname} (Dish)"})
            return found
    async def async_step_select_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            selected_device = next(d for d in self._discovered_devices if d['id'] == user_input['device_id'])
            return self.async_create_entry(title=selected_device['name'], data={CONF_COOKIE: self._cookie, CONF_ROUTER_ID: selected_device['id'], CONF_NAME: selected_device['name'], CONF_SCAN_INTERVAL: 60})
        return self.async_show_form(step_id='select_device', data_schema=vol.Schema({vol.Required('device_id'): vol.In({d['id']: d['name'] for d in self._discovered_devices})}))
