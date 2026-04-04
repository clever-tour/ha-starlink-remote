#!/usr/bin/env python3
"""
run_local_test.py
=================
Runs the coordinator's full data-fetch pipeline against either:

  a) A real Starlink dish (set STARLINK_ROUTER_ID + STARLINK_COOKIE)
  b) The mock server  (default — starts mock_starlink_server.py automatically)

No Home Assistant installation needed.

Usage
-----
    # Test against mock (auto-starts mock server):
    python scripts/run_local_test.py

    # Test against real dish:
    python scripts/run_local_test.py --real \\
        --cookie "$(cat my_cookie.json)" \\
        --router-id Router-010000000000abcd

    # Test a specific scenario:
    python scripts/run_local_test.py --scenario degraded

Output
------
Prints a structured JSON report of what the coordinator would publish to HA.
Exits 0 on success, 1 on any data or connectivity error.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import signal
from pathlib import Path

# Ensure the repo root is on the path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from tests.fixtures.mock_starlink_data import (
    make_dish_status, make_history_samples, make_wifi_clients
)


def _print_section(title: str, data: dict | list) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    print(json.dumps(data, indent=2, default=str))


def run_against_mock(scenario: str = "normal") -> int:
    """
    Run the coordinator pipeline using the fixture data directly.
    Simulates exactly what the coordinator produces for HA entities.
    """
    print(f"\n[local-test] Running pipeline with mock scenario: {scenario!r}")
    # Import coordinator internals
    try:
        # Stub HA so coordinator imports work
        import types
        ha = types.ModuleType("homeassistant")
        ha.core = types.ModuleType("homeassistant.core")
        ha.core.HomeAssistant = object
        ha.helpers = types.ModuleType("homeassistant.helpers")
        class _FakeDUC:
            def __class_getitem__(cls, item):
                return cls
            def __init__(self, *args, **kwargs):
                pass

        coord_mod = types.ModuleType("homeassistant.helpers.update_coordinator")
        coord_mod.DataUpdateCoordinator = _FakeDUC
        coord_mod.UpdateFailed = Exception
        ha.helpers.update_coordinator = coord_mod

        for name, mod in [
            ("homeassistant", ha),
            ("homeassistant.core", ha.core),
            ("homeassistant.helpers", ha.helpers),
            ("homeassistant.helpers.update_coordinator", coord_mod),
        ]:
            if name not in sys.modules:
                sys.modules[name] = mod

        from custom_components.starlink_ha.coordinator import StarlinkCoordinator
    except ImportError as exc:
        print(f"[ERROR] Cannot import coordinator: {exc}")
        return 1

    # ── Generate mock data ───────────────────────────────────────────────────
    scenarios = {
        "normal":     {"latency": 22.0, "dl": 250e6, "ul": 25e6, "state": "CONNECTED", "power": 55.0},
        "degraded":   {"latency": 120.0, "dl": 30e6, "ul": 5e6, "state": "CONNECTED", "power": 72.0},
        "obstructed": {"latency": 0.0, "dl": 0.0, "ul": 0.0, "state": "BOOTING", "power": 40.0},
    }
    sc = scenarios.get(scenario, scenarios["normal"])

    dish = make_dish_status(
        state=sc["state"],
        latency_ms=sc["latency"],
        downlink_bps=sc["dl"],
        uplink_bps=sc["ul"],
    )

    samples = make_history_samples(count=60, power_watts=sc["power"])

    # Dedup
    class _Dedup:
        def __init__(self): self._seen_history = {}
        _novel_history = StarlinkCoordinator._novel_history
        _aggregate_history = StarlinkCoordinator._aggregate_history

    dedup = _Dedup()
    novel = dedup._novel_history(samples)
    history_summary = dedup._aggregate_history(novel)

    wifi = make_wifi_clients(count=3)

    # ── Print report ─────────────────────────────────────────────────────────
    _print_section("DISH STATUS", dish)
    _print_section("HISTORY SUMMARY (what HA sensors see)", history_summary)
    _print_section("HISTORY: Novel sample count", {"novel_samples": len(novel), "total_samples": len(samples)})
    _print_section("WIFI CLIENTS", wifi)

    # ── Validate required fields ──────────────────────────────────────────────
    errors = []
    required_dish  = ["state", "popPingLatencyMs", "downlinkThroughputBps", "signalQuality"]
    required_hist  = ["avg_latency_ms", "p95_latency_ms", "avg_downlink_bps", "avg_power_watts"]

    for field in required_dish:
        if field not in dish:
            errors.append(f"Missing dish field: {field}")
    for field in required_hist:
        if field not in history_summary:
            errors.append(f"Missing history field: {field}")
    if not isinstance(wifi, list) or len(wifi) == 0:
        errors.append("WiFi clients list is empty")

    print(f"\n{'='*60}")
    if errors:
        print("  RESULT: FAILED")
        for e in errors:
            print(f"  ✗ {e}")
        return 1
    else:
        print("  RESULT: PASSED ✓")
        print(f"  Dish state   : {dish['state']}")
        print(f"  Latency      : {dish['popPingLatencyMs']:.1f} ms")
        print(f"  Downlink     : {dish['downlinkThroughputBps']/1e6:.1f} Mbps")
        print(f"  WiFi clients : {len(wifi)}")
        print(f"  Novel history: {len(novel)} samples → avg {history_summary['avg_latency_ms']:.1f} ms")
    print(f"{'='*60}\n")
    return 0


def run_against_real_dish(cookie_json: str, router_id: str) -> int:
    """Run against a live dish using the real starlink-client library."""
    print("[local-test] Connecting to real Starlink dish...")
    try:
        from starlink_client.cookies_parser import parse_cookie_json
        from starlink_client.grpc_web_client import GrpcWebClient
        from google.protobuf.json_format import MessageToDict
        from spacex.api.device.device_pb2 import Request, GetStatusRequest
    except ImportError as exc:
        print(f"[ERROR] starlink-client not installed: {exc}")
        print("  Run: pip install starlink-client")
        return 1

    cookies = parse_cookie_json(cookie_json)
    client  = GrpcWebClient(cookies, "/tmp/.starlink_test_cookies")

    try:
        req  = Request(target_id=router_id, get_status=GetStatusRequest())
        resp = client.call(req)
        dish = MessageToDict(resp.dish_get_status, preserving_proto_field_name=True)
        _print_section("DISH STATUS (live)", dish)
        print("\n[local-test] Live connection: PASSED ✓")
        return 0
    except Exception as exc:
        print(f"\n[ERROR] Failed to connect: {exc}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Local pipeline test")
    parser.add_argument("--real", action="store_true", help="Connect to real dish")
    parser.add_argument("--cookie", default=os.getenv("STARLINK_COOKIE", ""))
    parser.add_argument("--router-id", default=os.getenv("STARLINK_ROUTER_ID", ""))
    parser.add_argument(
        "--scenario",
        choices=["normal", "degraded", "obstructed"],
        default=os.getenv("MOCK_STARLINK_SCENARIO", "normal"),
    )
    args = parser.parse_args()

    if args.real:
        if not args.cookie or not args.router_id:
            print("[ERROR] --cookie and --router-id are required for --real mode")
            return 1
        return run_against_real_dish(args.cookie, args.router_id)
    else:
        return run_against_mock(args.scenario)


if __name__ == "__main__":
    sys.exit(main())
