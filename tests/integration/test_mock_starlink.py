"""
Integration tests: StarlinkCoordinator with a fully mocked starlink-client.

These tests exercise _fetch_all() end-to-end without needing a real dish
or a running HA instance.  We mock at the GrpcWebClient boundary.
"""
from __future__ import annotations

import sys
import types
import time
import pytest
from unittest.mock import MagicMock, patch

# ── HA stubs ─────────────────────────────────────────────────────────────────
def _stub_module(path, **attrs):
    parts = path.split(".")
    obj = None
    for i in range(len(parts)):
        full = ".".join(parts[: i + 1])
        if full not in sys.modules:
            m = types.ModuleType(full)
            sys.modules[full] = m
        obj = sys.modules[full]
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj

_stub_module("homeassistant")
_stub_module("homeassistant.core", HomeAssistant=MagicMock)
_stub_module("homeassistant.helpers")

class _FakeDUC:
    def __class_getitem__(cls, item): return cls
    def __init__(self, hass, logger, name, update_interval):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.data = None
        self.config_entry = None

_stub_module("homeassistant.helpers.update_coordinator",
             DataUpdateCoordinator=_FakeDUC,
             UpdateFailed=Exception)
_stub_module("homeassistant.config_entries", ConfigEntry=MagicMock)
_stub_module("homeassistant.const", Platform=types.SimpleNamespace(SENSOR="sensor", BINARY_SENSOR="binary_sensor"))
_stub_module("homeassistant.core", HomeAssistant=MagicMock, callback=lambda x: x)

from tests.fixtures.mock_starlink_data import (  # noqa: E402
    make_dish_status, make_history_samples, make_wifi_clients
)


# ── Build a minimal fake proto response ──────────────────────────────────────

def _make_proto_response(dish_status_dict, history_dict, wifi_dict, clients_list):
    """
    Build a fake protobuf Response-like object.
    MessageToDict is mocked to return our test dicts.
    """
    resp = MagicMock()
    # We mock MessageToDict globally so whatever field is accessed returns
    # our pre-cooked dict.
    resp.dish_get_status = MagicMock()
    resp.dish_get_history = MagicMock()
    resp.wifi_get_status = MagicMock()
    resp.wifi_get_clients = MagicMock()
    return resp


# ── Coordinator under test ────────────────────────────────────────────────────

def _make_coordinator():
    """Instantiate a StarlinkCoordinator with a fake config entry."""
    # Import late so stubs are in place
    from custom_components.starlink_ha.coordinator import StarlinkCoordinator

    entry = MagicMock()
    entry.entry_id = "test_entry_1"
    entry.data = {
        "name": "Test",
        "cookie": '{"test": true}',
        "router_id": "Router-000000000000",
        "cookie_dir": "/tmp/.starlink_test",
        "scan_interval": 60,
    }
    entry.options = {}
    entry.title = "Test"

    hass = MagicMock()
    coord = StarlinkCoordinator.__new__(StarlinkCoordinator)
    _FakeDUC.__init__(coord, hass, None, "test", None)
    coord._entry = entry
    coord._seen_history = {}
    return coord


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestHistoryParsing:
    """Test the static _parse_history method in isolation."""

    def test_returns_correct_count(self):
        from custom_components.starlink_ha.coordinator import StarlinkCoordinator

        n = 30
        fake_resp = MagicMock()
        fake_hist = {
            "popPingLatencyMs": [20.0] * n,
            "downlinkThroughputBps": [2e8] * n,
            "uplinkThroughputBps": [2e7] * n,
            "popPingDropRate": [0.005] * n,
            "powerIn": [55.0] * n,
        }

        def mock_to_dict(msg, **kwargs):
            return fake_hist

        samples = StarlinkCoordinator._parse_history(fake_resp, mock_to_dict)
        assert len(samples) == n

    def test_timestamps_are_ascending(self):
        from custom_components.starlink_ha.coordinator import StarlinkCoordinator

        n = 10
        fake_resp = MagicMock()
        fake_hist = {
            "popPingLatencyMs": [20.0] * n,
            "downlinkThroughputBps": [2e8] * n,
            "uplinkThroughputBps": [2e7] * n,
            "popPingDropRate": [0.0] * n,
            "powerIn": [50.0] * n,
        }

        samples = StarlinkCoordinator._parse_history(fake_resp, lambda m, **kw: fake_hist)
        timestamps = [s["timestamp"] for s in samples]
        assert timestamps == sorted(timestamps)

    def test_most_recent_sample_near_now(self):
        from custom_components.starlink_ha.coordinator import StarlinkCoordinator

        n = 60
        fake_hist = {
            "popPingLatencyMs": [20.0] * n,
            "downlinkThroughputBps": [2e8] * n,
            "uplinkThroughputBps": [2e7] * n,
            "popPingDropRate": [0.0] * n,
            "powerIn": [50.0] * n,
        }
        before = time.time()
        samples = StarlinkCoordinator._parse_history(MagicMock(), lambda m, **kw: fake_hist)
        after = time.time()
        newest = samples[-1]["timestamp"]
        assert before <= newest <= after + 1  # within 1s of now

    def test_empty_history_returns_empty_list(self):
        from custom_components.starlink_ha.coordinator import StarlinkCoordinator
        samples = StarlinkCoordinator._parse_history(MagicMock(), lambda m, **kw: {})
        assert samples == []


class TestDeduplicationPipeline:
    """Test novel_history + aggregate_history as a pipeline."""

    def test_pipeline_returns_summary_on_first_call(self):
        coord = _make_coordinator()
        samples = make_history_samples(count=60)
        novel = coord._novel_history(coord, samples)
        summary = coord._aggregate_history(coord, novel)
        assert summary["sample_count"] == 60
        assert summary["avg_latency_ms"] > 0

    def test_pipeline_returns_no_summary_on_repeat(self):
        coord = _make_coordinator()
        samples = make_history_samples(count=60)
        coord._novel_history(coord, samples)
        novel2 = coord._novel_history(coord, samples)
        assert novel2 == []

    def test_pipeline_accumulates_novel_samples_across_polls(self):
        coord = _make_coordinator()
        base = time.time()
        # Poll 1: samples 0-59
        s1 = make_history_samples(60, base_time=base + 59)
        coord._novel_history(coord, s1)
        # Poll 2: samples 30-89 (overlap 30, new 30)
        s2 = make_history_samples(60, base_time=base + 89)
        novel2 = coord._novel_history(coord, s2)
        assert len(novel2) == 30
