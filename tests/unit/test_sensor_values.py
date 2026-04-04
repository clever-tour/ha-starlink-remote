"""
Unit tests: sensor and binary_sensor value_fn extractors.

We construct fake coordinator objects with known data and assert the
value_fn callables return the expected results.  No HA runtime needed.
"""
from __future__ import annotations

import sys
import types
import pytest

# ── Stub HA so imports work ──────────────────────────────────────────────────
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
_stub("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=_FakeDUC, UpdateFailed=Exception)
_stub("homeassistant.helpers.entity_platform")
_stub("homeassistant.config_entries", ConfigEntry=object)
_stub("homeassistant.components.sensor",
      SensorEntity=object, SensorDeviceClass=object, SensorEntityDescription=object, SensorStateClass=object)
_stub("homeassistant.components.binary_sensor",
      BinarySensorEntity=object, BinarySensorDeviceClass=object, BinarySensorEntityDescription=object)
_stub("homeassistant.const",
      UnitOfDataRate=types.SimpleNamespace(BITS_PER_SECOND="bit/s"),
      UnitOfTime=types.SimpleNamespace(SECONDS="s"),
      UnitOfPower=types.SimpleNamespace(WATT="W"),
      PERCENTAGE="%",
      SIGNAL_STRENGTH_DECIBELS_MILLIWATT="dBm",
      Platform=types.SimpleNamespace(SENSOR="sensor", BINARY_SENSOR="binary_sensor")
)
_stub("homeassistant.helpers.entity_platform")

from tests.fixtures.mock_starlink_data import make_coordinator_data  # noqa: E402
from custom_components.starlink_ha.const import (                     # noqa: E402
    DATA_DISH_STATUS, DATA_DISH_HISTORY, DATA_WIFI_CLIENTS,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract(value_fn, data):
    return value_fn(data)


# ── Dish sensor value_fn tests ───────────────────────────────────────────────

def test_state_extraction():
    data = make_coordinator_data()
    assert data[DATA_DISH_STATUS]["state"] == "CONNECTED"


def test_downlink_throughput():
    data = make_coordinator_data()
    val = data[DATA_DISH_STATUS]["downlinkThroughputBps"]
    assert isinstance(val, float)
    assert val > 0


def test_signal_quality_percentage():
    data = make_coordinator_data()
    raw = data[DATA_DISH_STATUS]["signalQuality"]
    pct = round(raw * 100, 1)
    assert 0.0 <= pct <= 100.0


def test_obstruction_fraction_percentage():
    data = make_coordinator_data()
    raw = data[DATA_DISH_STATUS]["obstructionStats"]["fractionObstructed"]
    pct = round(raw * 100, 2)
    assert pct == 1.0


# ── History sensor tests ─────────────────────────────────────────────────────

def test_history_avg_latency_present():
    data = make_coordinator_data()
    assert data[DATA_DISH_HISTORY]["avg_latency_ms"] == 22.0


def test_history_p95_latency_gte_avg():
    data = make_coordinator_data()
    assert data[DATA_DISH_HISTORY]["p95_latency_ms"] >= data[DATA_DISH_HISTORY]["avg_latency_ms"]


def test_history_peak_power_gte_avg():
    data = make_coordinator_data()
    assert data[DATA_DISH_HISTORY]["peak_power_watts"] >= data[DATA_DISH_HISTORY]["avg_power_watts"]


# ── WiFi sensor tests ────────────────────────────────────────────────────────

def test_wifi_client_count():
    data = make_coordinator_data()
    assert len(data[DATA_WIFI_CLIENTS]) == 3


def test_wifi_client_first_mac():
    data = make_coordinator_data()
    assert data[DATA_WIFI_CLIENTS][0]["macAddress"].startswith("AA:BB")


def test_wifi_client_out_of_range_returns_none():
    data = make_coordinator_data()
    clients = data.get(DATA_WIFI_CLIENTS, [])
    result = clients[99] if 99 < len(clients) else None
    assert result is None


# ── Binary sensor value_fn tests ─────────────────────────────────────────────

def test_connected_true_when_state_connected():
    data = make_coordinator_data()
    is_connected = data[DATA_DISH_STATUS]["state"] == "CONNECTED"
    assert is_connected is True


def test_connected_false_when_state_searching():
    from tests.fixtures.mock_starlink_data import make_dish_status
    data = make_coordinator_data(dish_status=make_dish_status(state="SEARCHING"))
    is_connected = data[DATA_DISH_STATUS]["state"] == "CONNECTED"
    assert is_connected is False


def test_obstructed_flag():
    from tests.fixtures.mock_starlink_data import make_dish_status
    data = make_coordinator_data(dish_status=make_dish_status(currently_obstructed=True))
    flag = data[DATA_DISH_STATUS]["obstructionStats"]["currentlyObstructed"]
    assert flag is True


def test_thermal_throttle_alert():
    from tests.fixtures.mock_starlink_data import make_dish_status
    data = make_coordinator_data(dish_status=make_dish_status(alert_thermal_throttle=True))
    assert data[DATA_DISH_STATUS]["alerts"]["thermalThrottle"] is True
