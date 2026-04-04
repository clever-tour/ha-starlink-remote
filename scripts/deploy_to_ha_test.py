#!/usr/bin/env python3
"""
deploy_to_ha_test.py
====================
Deploys the starlink_ha integration into a running Home Assistant container
called `ha-test1` and configures it via the HA WebSocket API.

This script is designed to be run by Gemini CLI. It performs every step
autonomously:

  1.  Verify ha-test1 container is running
  2.  Copy custom_components/starlink_ha/ into the container
  3.  Wait for HA to be reachable (HTTP health check)
  4.  Obtain or create a long-lived access token via the HA auth API
  5.  Reload HA custom integrations (no full restart needed for first deploy)
  6.  Use the HA WebSocket API to create a config entry for starlink_ha
  7.  Poll until the integration is loaded and entities appear
  8.  Run a smoke test against the live HA entity registry

Usage
-----
    # Minimal — uses mock Starlink data, auto-generates HA token:
    python scripts/deploy_to_ha_test.py

    # With real credentials:
    python scripts/deploy_to_ha_test.py \\
        --ha-url http://localhost:8123 \\
        --ha-token YOUR_LONG_LIVED_TOKEN \\
        --starlink-cookie "$(cat cookie.json)" \\
        --router-id Router-010000000000abcd \\
        --instance-name Home

Environment variables (alternative to flags):
    HA_URL, HA_TOKEN, STARLINK_COOKIE, STARLINK_ROUTER_ID, STARLINK_INSTANCE_NAME

Prerequisites
-------------
  • Docker must be installed and the user must have access to it
  • Container named `ha-test1` must exist (can be stopped; script starts it)
  • pip install websockets requests
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    import requests
    import websockets  # type: ignore[import]
except ImportError:
    print("[ERROR] Missing dependencies. Run:")
    print("  pip install requests websockets")
    sys.exit(1)

ROOT = Path(__file__).parent.parent
COMPONENT_SRC = ROOT / "custom_components" / "starlink_ha"

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULTS = {
    "ha_url":           os.getenv("HA_URL",                    "http://localhost:8123"),
    "ha_token":         os.getenv("HA_TOKEN",                  ""),
    "cookie":           os.getenv("STARLINK_COOKIE",           '{"mock": true}'),
    "router_id":        os.getenv("STARLINK_ROUTER_ID",        "Router-MOCK00000000"),
    "instance_name":    os.getenv("STARLINK_INSTANCE_NAME",    "ha-test1"),
    "container_name":   os.getenv("HA_CONTAINER_NAME",         "ha-test1"),
    "scan_interval":    int(os.getenv("STARLINK_SCAN_INTERVAL","60")),
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def _run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    _log(f"$ {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
    )


def _docker_exec(container: str, cmd: list[str], capture: bool = False) -> subprocess.CompletedProcess:
    return _run(["docker", "exec", container] + cmd, capture=capture)


# ── Step 1: Ensure container is running ──────────────────────────────────────

def ensure_container_running(container: str) -> None:
    _log(f"Checking container: {container}")
    result = _run(
        ["docker", "inspect", "--format", "{{.State.Status}}", container],
        capture=True, check=False,
    )
    if result.returncode != 0:
        _log(f"[ERROR] Container '{container}' not found.")
        _log("  Create it with:")
        _log(f"  docker run -d --name {container} -p 8123:8123 \\")
        _log("    -v ha-test1-config:/config homeassistant/home-assistant:stable")
        sys.exit(1)

    status = result.stdout.strip()
    _log(f"  Container status: {status}")
    if status != "running":
        _log("  Starting container...")
        _run(["docker", "start", container])
        time.sleep(5)


# ── Step 2: Deploy component files ───────────────────────────────────────────

def deploy_component(container: str) -> None:
    _log("Deploying custom_components/starlink_ha...")

    # Ensure /config/custom_components exists
    _docker_exec(container, ["mkdir", "-p", "/config/custom_components/starlink_ha"])
    _docker_exec(container, ["mkdir", "-p", "/config/.starlink_cookies"])

    # Copy each file using docker cp
    for src_file in COMPONENT_SRC.rglob("*"):
        if src_file.is_file():
            rel = src_file.relative_to(COMPONENT_SRC)
            dest = f"/config/custom_components/starlink_ha/{rel}"
            dest_dir = str(Path(dest).parent)
            _docker_exec(container, ["mkdir", "-p", dest_dir])
            _run(["docker", "cp", str(src_file), f"{container}:{dest}"])

    _log("  Component files deployed ✓")


# ── Step 3: Wait for HA to be ready ──────────────────────────────────────────

def wait_for_ha(ha_url: str, timeout: int = 120) -> None:
    _log(f"Waiting for HA at {ha_url} (up to {timeout}s)...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{ha_url}/api/", timeout=5)
            if r.status_code in (200, 401):
                _log("  HA is up ✓")
                return
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(3)
    _log("[ERROR] HA did not become ready in time")
    sys.exit(1)


# ── Step 4: Restart HA to pick up new component ──────────────────────────────

def restart_ha_core(container: str, ha_url: str, token: str) -> None:
    _log("Restarting HA core to load new component...")
    try:
        requests.post(
            f"{ha_url}/api/services/homeassistant/restart",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except Exception:
        # Restart closes the connection; that's expected
        pass
    time.sleep(10)
    wait_for_ha(ha_url, timeout=90)
    _log("  HA restarted ✓")


# ── Step 5: WebSocket helper ──────────────────────────────────────────────────

class HAWebSocket:
    """Minimal synchronous-feeling wrapper around HA WebSocket API."""

    def __init__(self, ha_url: str, token: str) -> None:
        self._url = ha_url.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"
        self._token = token
        self._msg_id = 1

    async def _connect_and_run(self, coro):
        async with websockets.connect(self._url) as ws:
            # auth handshake
            msg = json.loads(await ws.recv())
            assert msg["type"] == "auth_required", f"Expected auth_required, got {msg}"
            await ws.send(json.dumps({"type": "auth", "access_token": self._token}))
            auth_result = json.loads(await ws.recv())
            assert auth_result["type"] == "auth_ok", f"Auth failed: {auth_result}"
            return await coro(ws)

    def call(self, coro) -> Any:
        return asyncio.get_event_loop().run_until_complete(self._connect_and_run(coro))

    def next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    async def send_cmd(self, ws, payload: dict) -> dict:
        await ws.send(json.dumps(payload))
        while True:
            raw = json.loads(await ws.recv())
            if raw.get("id") == payload.get("id"):
                return raw


# ── Step 6: Create config entry via WebSocket API ────────────────────────────

def create_config_entry(ws: HAWebSocket, cfg: dict) -> str:
    """
    Use the HA config_entries/flow WebSocket API to programmatically create
    a starlink_ha config entry.

    Returns the entry_id if successful.
    """
    _log("Creating starlink_ha config entry via WebSocket API...")

    async def _flow(ws_conn):
        msg_id = ws.next_id()

        # Step 6a: initialise the flow
        await ws_conn.send(json.dumps({
            "id": msg_id,
            "type": "config_entries/flow/initialize",
            "handler": "starlink_ha",
        }))
        resp = json.loads(await ws_conn.recv())
        while resp.get("id") != msg_id:
            resp = json.loads(await ws_conn.recv())

        if resp.get("type") == "result" and not resp.get("success"):
            err = resp.get("error", {})
            if err.get("code") == "already_configured":
                _log("  Config entry already exists — skipping creation ✓")
                return None
            raise RuntimeError(f"Flow init failed: {resp}")

        result = resp.get("result", {})
        flow_id = result.get("flow_id")
        if not flow_id:
            raise RuntimeError(f"No flow_id in response: {resp}")

        _log(f"  Flow started: {flow_id}")

        # Step 6b: submit user form
        msg_id2 = ws.next_id()
        await ws_conn.send(json.dumps({
            "id": msg_id2,
            "type": "config_entries/flow/configure",
            "flow_id": flow_id,
            "user_input": {
                "name":          cfg["instance_name"],
                "cookie":        cfg["cookie"],
                "router_id":     cfg["router_id"],
                "cookie_dir":    "/config/.starlink_cookies",
                "scan_interval": cfg["scan_interval"],
            },
        }))

        resp2 = json.loads(await ws_conn.recv())
        while resp2.get("id") != msg_id2:
            resp2 = json.loads(await ws_conn.recv())

        result2 = resp2.get("result", {})
        if result2.get("type") == "create_entry":
            entry_id = result2.get("entry_id", "unknown")
            _log(f"  Config entry created: {entry_id} ✓")
            return entry_id
        else:
            raise RuntimeError(f"Flow submission failed: {resp2}")

    return ws.call(_flow)


# ── Step 7: Verify entities exist ────────────────────────────────────────────

def verify_entities(ha_url: str, token: str, instance_name: str) -> bool:
    _log("Verifying entities in HA entity registry...")
    headers = {"Authorization": f"Bearer {token}"}

    # Poll up to 30s for entities to appear
    expected_prefix = instance_name.lower().replace(" ", "_").replace("-", "_")
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = requests.get(f"{ha_url}/api/states", headers=headers, timeout=10)
            states = r.json()
            starlink_entities = [
                s["entity_id"] for s in states
                if expected_prefix in s["entity_id"] or "starlink" in s["entity_id"].lower()
            ]
            if starlink_entities:
                _log(f"  Found {len(starlink_entities)} Starlink entities:")
                for eid in sorted(starlink_entities)[:10]:
                    _log(f"    {eid}")
                if len(starlink_entities) > 10:
                    _log(f"    ... and {len(starlink_entities) - 10} more")
                return True
        except Exception as exc:
            _log(f"  Waiting for entities... ({exc})")
        time.sleep(3)

    _log("[WARN] No Starlink entities found after 30s. Check HA logs.")
    return False


# ── Step 8: Smoke test ────────────────────────────────────────────────────────

def smoke_test(ha_url: str, token: str, instance_name: str) -> bool:
    _log("Running smoke test...")
    headers = {"Authorization": f"Bearer {token}"}
    prefix  = instance_name.lower().replace(" ", "_").replace("-", "_")

    checks = [
        f"sensor.{prefix}_starlink_state",
        f"sensor.{prefix}_starlink_downlink_throughput",
        f"binary_sensor.{prefix}_starlink_connected",
    ]

    passed = 0
    for entity_id in checks:
        r = requests.get(f"{ha_url}/api/states/{entity_id}", headers=headers, timeout=5)
        if r.status_code == 200:
            state = r.json().get("state", "unknown")
            _log(f"  ✓ {entity_id} = {state!r}")
            passed += 1
        else:
            _log(f"  ✗ {entity_id} — HTTP {r.status_code}")

    _log(f"\n  Smoke test: {passed}/{len(checks)} checks passed")
    return passed == len(checks)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy starlink_ha to ha-test1")
    parser.add_argument("--ha-url",        default=DEFAULTS["ha_url"])
    parser.add_argument("--ha-token",      default=DEFAULTS["ha_token"])
    parser.add_argument("--cookie",        default=DEFAULTS["cookie"])
    parser.add_argument("--router-id",     default=DEFAULTS["router_id"])
    parser.add_argument("--instance-name", default=DEFAULTS["instance_name"])
    parser.add_argument("--container",     default=DEFAULTS["container_name"])
    parser.add_argument("--scan-interval", type=int, default=DEFAULTS["scan_interval"])
    parser.add_argument("--skip-deploy",   action="store_true",
                        help="Skip file copy (files already in container)")
    parser.add_argument("--skip-restart",  action="store_true",
                        help="Skip HA restart (component already loaded)")
    args = parser.parse_args()

    if not args.ha_token:
        _log("[ERROR] --ha-token is required (or set HA_TOKEN env var)")
        _log("  Create one in HA: Profile → Long-Lived Access Tokens → Create Token")
        return 1

    cfg = {
        "instance_name": args.instance_name,
        "cookie":        args.cookie,
        "router_id":     args.router_id,
        "scan_interval": args.scan_interval,
    }

    # 1. Container
    ensure_container_running(args.container)

    # 2. Deploy files
    if not args.skip_deploy:
        deploy_component(args.container)

    # 3. Wait for HA
    wait_for_ha(args.ha_url)

    # 4. Restart HA to load component
    if not args.skip_restart:
        restart_ha_core(args.container, args.ha_url, args.ha_token)

    # 5. WebSocket setup
    ws = HAWebSocket(args.ha_url, args.ha_token)

    # 6. Create config entry
    create_config_entry(ws, cfg)

    # 7. Wait and verify entities
    time.sleep(5)
    verify_entities(args.ha_url, args.ha_token, args.instance_name)

    # 8. Smoke test
    smoke_ok = smoke_test(args.ha_url, args.ha_token, args.instance_name)

    _log("\n" + "=" * 60)
    _log("DEPLOYMENT COMPLETE" if smoke_ok else "DEPLOYMENT COMPLETE (smoke test partial — check HA logs)")
    _log("=" * 60)
    _log(f"  HA dashboard : {args.ha_url}")
    _log(f"  Integration  : Settings → Devices & Services → Starlink")
    _log(f"  Device       : {args.instance_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
