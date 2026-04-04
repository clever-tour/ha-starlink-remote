#!/usr/bin/env python3
"""
mock_starlink_server.py
=======================
A lightweight HTTP server that impersonates the starlink-client's
GrpcWebClient.call() endpoint.  Used for:

  1. Running the full coordinator pipeline locally without a real dish.
  2. Integration testing the HA extension inside ha-test1.

The server exposes the same JSON shapes that MessageToDict(proto) returns
so the coordinator can run completely unmodified.

Usage
-----
    python scripts/mock_starlink_server.py [--port 9200] [--scenario degraded]

Scenarios
---------
  normal     — healthy connection, good signal           (default)
  degraded   — high latency, some packet loss
  obstructed — currently obstructed, poor signal
  offline    — returns HTTP 503 so coordinator sees UpdateFailed

Environment variable override:
    MOCK_STARLINK_SCENARIO=degraded python scripts/mock_starlink_server.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import math
import random
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

# ── Scenario data ─────────────────────────────────────────────────────────────

_SCENARIOS: dict[str, dict[str, Any]] = {
    "normal": {
        "state": "CONNECTED",
        "uptime_s": 86400,
        "latency_ms": 22.0,
        "downlink_bps": 250_000_000.0,
        "uplink_bps": 25_000_000.0,
        "snr": 8.5,
        "signal_quality": 0.92,
        "fraction_obstructed": 0.01,
        "currently_obstructed": False,
        "alert_thermal_throttle": False,
        "alert_roaming": False,
        "power_watts": 55.0,
    },
    "degraded": {
        "state": "CONNECTED",
        "uptime_s": 3600,
        "latency_ms": 120.0,
        "downlink_bps": 30_000_000.0,
        "uplink_bps": 5_000_000.0,
        "snr": 3.2,
        "signal_quality": 0.61,
        "fraction_obstructed": 0.15,
        "currently_obstructed": False,
        "alert_thermal_throttle": True,
        "alert_roaming": False,
        "power_watts": 72.0,
    },
    "obstructed": {
        "state": "BOOTING",
        "uptime_s": 120,
        "latency_ms": 0.0,
        "downlink_bps": 0.0,
        "uplink_bps": 0.0,
        "snr": 0.0,
        "signal_quality": 0.0,
        "fraction_obstructed": 0.75,
        "currently_obstructed": True,
        "alert_thermal_throttle": False,
        "alert_roaming": False,
        "power_watts": 40.0,
    },
}


def _dish_status(sc: dict) -> dict:
    return {
        "state": sc["state"],
        "deviceState": {"uptimeS": sc["uptime_s"]},
        "deviceInfo": {
            "id": "ut01000000-00000000-MOCK1234",
            "hardwareVersion": "rev3_proto3",
            "softwareVersion": "2024.12.0.mock",
            "countryCode": "NL",
        },
        "popPingLatencyMs": sc["latency_ms"] + random.uniform(-2, 2),
        "downlinkThroughputBps": sc["downlink_bps"] * random.uniform(0.9, 1.1),
        "uplinkThroughputBps": sc["uplink_bps"] * random.uniform(0.9, 1.1),
        "snr": sc["snr"],
        "signalQuality": sc["signal_quality"],
        "obstructionStats": {
            "fractionObstructed": sc["fraction_obstructed"],
            "currentlyObstructed": sc["currently_obstructed"],
        },
        "alerts": {
            "motorsStuck": False,
            "thermalThrottle": sc["alert_thermal_throttle"],
            "thermalShutdown": False,
            "mastNotNearVertical": False,
            "unexpectedLocation": False,
            "slowEthernetSpeeds": False,
            "roaming": sc["alert_roaming"],
        },
    }


def _history(sc: dict, n: int = 60) -> dict:
    base_lat = sc["latency_ms"]
    base_power = sc["power_watts"]
    now = time.time()
    return {
        "popPingLatencyMs":      [max(0, base_lat + math.sin(i * 0.3) * 5 + random.uniform(-1, 1)) for i in range(n)],
        "downlinkThroughputBps": [max(0, sc["downlink_bps"] * (0.95 + 0.1 * math.sin(i * 0.1))) for i in range(n)],
        "uplinkThroughputBps":   [max(0, sc["uplink_bps"]   * (0.95 + 0.1 * math.sin(i * 0.1))) for i in range(n)],
        "popPingDropRate":       [0.005 if sc["signal_quality"] > 0.5 else 0.08 + random.uniform(0, 0.05) for _ in range(n)],
        "powerIn":               [base_power + random.uniform(-2, 2) for _ in range(n)],
        # Not a real proto field but handy for timestamp reconstruction
        "_base_time": now,
        "_count": n,
    }


def _wifi_clients(count: int = 4) -> dict:
    clients = [
        {
            "macAddress": f"AA:BB:CC:DD:EE:{i:02X}",
            "ipAddress": f"192.168.1.{100 + i}",
            "friendlyName": f"mock-device-{i}",
            "rxStats": {"rssi": -55.0 - i * 4, "rateMbps": 144.0},
            "txStats": {"rateMbps": 144.0},
            "radioId": i % 2,
            "connectedTimeS": 3600 * (i + 1),
        }
        for i in range(count)
    ]
    return {"clients": clients}


def _wifi_status() -> dict:
    return {
        "basicServiceSets": [
            {"ssid": "MockStarlink-5G",  "band": "5GHz"},
            {"ssid": "MockStarlink-2.4", "band": "2.4GHz"},
        ]
    }


# ── Request handler ───────────────────────────────────────────────────────────

class MockHandler(BaseHTTPRequestHandler):
    scenario: str = "normal"

    def log_message(self, fmt, *args):  # pylint: disable=arguments-differ
        print(f"[mock] {self.address_string()} {fmt % args}", file=sys.stderr)

    def do_POST(self):
        if self.scenario == "offline":
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b"Service Unavailable")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        try:
            req = json.loads(body) if body else {}
        except json.JSONDecodeError:
            req = {}

        sc = _SCENARIOS[self.scenario]

        # Route based on path / request content
        path = self.path.lower()
        if "history" in path or req.get("dish_get_history") is not None:
            payload = _history(sc)
        elif "wifi_get_clients" in path or req.get("wifi_get_clients") is not None:
            payload = _wifi_clients()
        elif "wifi" in path or req.get("wifi_get_status") is not None:
            payload = _wifi_status()
        else:
            payload = _dish_status(sc)

        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        """Health check endpoint."""
        body = json.dumps({"status": "ok", "scenario": self.scenario}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Mock Starlink gRPC server")
    parser.add_argument("--port", type=int, default=9200)
    parser.add_argument(
        "--scenario",
        choices=list(_SCENARIOS) + ["offline"],
        default=os.getenv("MOCK_STARLINK_SCENARIO", "normal"),
    )
    args = parser.parse_args()

    MockHandler.scenario = args.scenario
    server = HTTPServer(("0.0.0.0", args.port), MockHandler)
    print(f"[mock] Starlink mock server: scenario={args.scenario} port={args.port}")
    print(f"[mock] Health: http://localhost:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[mock] Stopped.")


if __name__ == "__main__":
    main()
