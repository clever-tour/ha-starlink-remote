"""
Unit tests: config_flow schema validation and const values.
"""
from __future__ import annotations

import sys
import types
import pytest
import voluptuous as vol

# ── Stub HA ──────────────────────────────────────────────────────────────────
def _stub(mod_path, **attrs):
    parts = mod_path.split(".")
    parent = None
    for i, part in enumerate(parts):
        full = ".".join(parts[: i + 1])
        if full not in sys.modules:
            m = types.ModuleType(full)
            if parent:
                setattr(parent, part, m)
            sys.modules[full] = m
        parent = sys.modules[full]
    for k, v in attrs.items():
        setattr(parent, k, v)
    return parent

class _FakeDUC:
    def __class_getitem__(cls, item): return cls
    def __init__(self, *args, **kwargs): pass

_stub("homeassistant.core", HomeAssistant=object, callback=lambda x: x)
_stub("homeassistant.config_entries", ConfigEntry=object)
_stub("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=_FakeDUC, UpdateFailed=Exception)
_stub("homeassistant.const", Platform=types.SimpleNamespace(SENSOR="sensor", BINARY_SENSOR="binary_sensor"))

from custom_components.starlink_ha.const import (
    MIN_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_COOKIE_DIR,
    CONF_NAME,
    CONF_COOKIE,
    CONF_ROUTER_ID,
    CONF_SCAN_INTERVAL,
    CONF_COOKIE_DIR,
)


def _schema():
    """Re-create the config flow schema directly so we can test validation."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME): str,
            vol.Required(CONF_COOKIE): str,
            vol.Required(CONF_ROUTER_ID): str,
            vol.Optional(CONF_COOKIE_DIR, default=DEFAULT_COOKIE_DIR): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
            ),
        }
    )


def _valid_input(**overrides):
    base = {
        CONF_NAME: "Test",
        CONF_COOKIE: '{"token": "abc"}',
        CONF_ROUTER_ID: "Router-010000000000abcd",
    }
    return {**base, **overrides}


def test_valid_input_passes():
    schema = _schema()
    result = schema(_valid_input())
    assert result[CONF_NAME] == "Test"
    assert result[CONF_SCAN_INTERVAL] == DEFAULT_SCAN_INTERVAL


def test_scan_interval_below_minimum_rejected():
    schema = _schema()
    with pytest.raises(vol.Invalid):
        schema(_valid_input(**{CONF_SCAN_INTERVAL: MIN_SCAN_INTERVAL - 1}))


def test_scan_interval_at_minimum_accepted():
    schema = _schema()
    result = schema(_valid_input(**{CONF_SCAN_INTERVAL: MIN_SCAN_INTERVAL}))
    assert result[CONF_SCAN_INTERVAL] == MIN_SCAN_INTERVAL


def test_scan_interval_above_maximum_rejected():
    schema = _schema()
    with pytest.raises(vol.Invalid):
        schema(_valid_input(**{CONF_SCAN_INTERVAL: MAX_SCAN_INTERVAL + 1}))


def test_missing_required_name_rejected():
    schema = _schema()
    with pytest.raises(vol.Invalid):
        schema({CONF_COOKIE: '{}', CONF_ROUTER_ID: "Router-abc"})


def test_defaults_applied():
    schema = _schema()
    result = schema(_valid_input())
    assert result[CONF_COOKIE_DIR] == DEFAULT_COOKIE_DIR
    assert result[CONF_SCAN_INTERVAL] == DEFAULT_SCAN_INTERVAL
