"""
Unit tests: StarlinkCoordinator history deduplication.
No Home Assistant or starlink-client needed — pure Python logic.
"""
from __future__ import annotations

import sys
import types
import time
import pytest

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
_stub("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=_FakeDUC, UpdateFailed=Exception)
_stub("homeassistant.config_entries", ConfigEntry=object)
_stub("homeassistant.const", Platform=types.SimpleNamespace(SENSOR="sensor", BINARY_SENSOR="binary_sensor"))

from custom_components.starlink_ha.coordinator import StarlinkCoordinator  # noqa: E402
from tests.fixtures.mock_starlink_data import make_history_samples           # noqa: E402


# ── Minimal stub that exposes the dedup methods ──────────────────────────────
class FakeCoord:
    def __init__(self):
        self._seen_history: dict[int, float] = {}

    _novel_history   = StarlinkCoordinator._novel_history
    _aggregate_history = StarlinkCoordinator._aggregate_history


# ── Tests ────────────────────────────────────────────────────────────────────

def test_first_batch_entirely_novel():
    c = FakeCoord()
    samples = make_history_samples(count=30)
    novel = c._novel_history(samples)
    assert len(novel) == 30


def test_identical_second_batch_is_zero():
    c = FakeCoord()
    samples = make_history_samples(count=30)
    c._novel_history(samples)
    assert c._novel_history(samples) == []


def test_partial_overlap_returns_only_new():
    c = FakeCoord()
    base = 1_000_000.0
    c._novel_history(make_history_samples(count=30, base_time=base + 29))
    # Second poll: overlaps first 20, adds 10 fresh ones
    novel = c._novel_history(make_history_samples(count=30, base_time=base + 49))
    assert len(novel) == 20


def test_seen_set_pruned_after_retention(monkeypatch):
    c = FakeCoord()
    old_time = time.time() - 7200  # 2 hours ago
    samples = make_history_samples(count=5, base_time=old_time + 4)
    c._novel_history(samples)
    # The samples are now in _seen_history with timestamps from 2 hours ago.
    # The _novel_history call just ran and pruned nothing because those were the newest.
    # Wait, the pruning happens AFTER adding new ones.
    
    # If we call it again with current time, the old ones should be pruned.
    c._novel_history([], now=time.time()) # trigger pruning with current time
    
    # Now same old samples should be treated as novel again
    novel = c._novel_history(samples)
    assert len(novel) == 5


def test_aggregate_computes_p95():
    c = FakeCoord()
    samples = [
        {
            "timestamp": float(i),
            "pop_ping_latency_ms": float(i + 1),   # 1..100
            "downlink_throughput_bps": 1e8,
            "uplink_throughput_bps": 1e7,
            "ping_drop_rate": 0.0,
            "power_input_watts": 55.0,
        }
        for i in range(100)
    ]
    agg = c._aggregate_history(samples)
    assert agg["sample_count"] == 100
    assert agg["p95_latency_ms"] == 96.0
    assert agg["avg_power_watts"] == 55.0
    assert agg["peak_power_watts"] == 55.0


def test_aggregate_empty_returns_empty_dict():
    c = FakeCoord()
    assert c._aggregate_history([]) == {}


def test_aggregate_single_sample():
    c = FakeCoord()
    samples = make_history_samples(count=1)
    agg = c._aggregate_history(samples)
    assert agg["sample_count"] == 1
    assert agg["coverage_seconds"] == 1
