"""
Shared test fixtures — realistic mock payloads that mirror what the
starlink-client library returns after protobuf → dict conversion.

Use these in both unit and integration tests to keep fixture data in
one place.  Update here when the dish firmware changes field names.
"""
from __future__ import annotations

import time
from typing import Any


def make_dish_status(
    state: str = "CONNECTED",
    uptime_s: int = 86400,
    latency_ms: float = 22.5,
    downlink_bps: float = 250_000_000.0,
    uplink_bps: float = 25_000_000.0,
    snr: float = 8.5,
    signal_quality: float = 0.92,
    fraction_obstructed: float = 0.01,
    currently_obstructed: bool = False,
    alert_thermal_throttle: bool = False,
    alert_roaming: bool = False,
) -> dict[str, Any]:
    """Return a realistic dish_get_status dict (proto → MessageToDict output)."""
    return {
        "state": state,
        "deviceState": {"uptimeS": uptime_s},
        "deviceInfo": {
            "id": "ut01000000-00000000-00112233",
            "hardwareVersion": "rev3_proto3",
            "softwareVersion": "2024.12.0.cr54321",
            "countryCode": "NL",
        },
        "popPingLatencyMs": latency_ms,
        "downlinkThroughputBps": downlink_bps,
        "uplinkThroughputBps": uplink_bps,
        "snr": snr,
        "signalQuality": signal_quality,
        "obstructionStats": {
            "fractionObstructed": fraction_obstructed,
            "currentlyObstructed": currently_obstructed,
        },
        "alerts": {
            "motorsStuck": False,
            "thermalThrottle": alert_thermal_throttle,
            "thermalShutdown": False,
            "mastNotNearVertical": False,
            "unexpectedLocation": False,
            "slowEthernetSpeeds": False,
            "roaming": alert_roaming,
        },
    }


def make_history_samples(
    count: int = 60,
    base_time: float | None = None,
    latency_ms: float = 20.0,
    downlink_bps: float = 200_000_000.0,
    uplink_bps: float = 20_000_000.0,
    ping_drop_rate: float = 0.005,
    power_watts: float = 55.0,
) -> list[dict[str, Any]]:
    """Return `count` history sample dicts at 1-second resolution."""
    t = base_time or time.time()
    return [
        {
            "timestamp": t - (count - 1 - i),
            "pop_ping_latency_ms": latency_ms + (i % 5),
            "downlink_throughput_bps": downlink_bps,
            "uplink_throughput_bps": uplink_bps,
            "ping_drop_rate": ping_drop_rate,
            "power_input_watts": power_watts,
        }
        for i in range(count)
    ]


def make_wifi_clients(count: int = 3) -> list[dict[str, Any]]:
    """Return a list of connected WiFi client dicts."""
    bands = ["2.4GHz", "5GHz"]
    return [
        {
            "macAddress": f"AA:BB:CC:DD:EE:{i:02X}",
            "ipAddress": f"192.168.1.{100 + i}",
            "friendlyName": f"device-{i}",
            "rxStats": {"rssi": -55.0 - i * 3, "rateMbps": 144.0},
            "txStats": {"rateMbps": 144.0},
            "radioId": i % 2,
            "connectedTimeS": 3600 * (i + 1),
        }
        for i in range(count)
    ]


def make_coordinator_data(
    dish_status: dict | None = None,
    history_summary: dict | None = None,
    wifi_clients: list | None = None,
    wifi_status: dict | None = None,
) -> dict[str, Any]:
    """Return a full coordinator.data dict as HA would see it after a poll."""
    from custom_components.starlink_ha.const import (
        DATA_DISH_STATUS,
        DATA_DISH_HISTORY,
        DATA_WIFI_CLIENTS,
        DATA_WIFI_STATUS,
    )
    return {
        DATA_DISH_STATUS: dish_status or make_dish_status(),
        DATA_DISH_HISTORY: history_summary or {
            "sample_count": 60,
            "avg_latency_ms": 22.0,
            "p95_latency_ms": 28.0,
            "avg_downlink_bps": 220_000_000.0,
            "avg_uplink_bps": 22_000_000.0,
            "avg_ping_drop_rate": 0.005,
            "avg_power_watts": 55.0,
            "peak_power_watts": 62.0,
            "coverage_seconds": 60,
        },
        DATA_WIFI_CLIENTS: wifi_clients if wifi_clients is not None else make_wifi_clients(),
        DATA_WIFI_STATUS: wifi_status or {
            "basicServiceSets": [{"ssid": "Starlink-Home", "band": "2.4GHz"}]
        },
    }
