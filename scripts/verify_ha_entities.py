#!/usr/bin/env python3
"""
verify_ha_entities.py
=====================
Queries a running HA instance and prints a full report of all
starlink_ha entities: their states, last_changed timestamps, and
any entities stuck as 'unavailable' or 'unknown'.

Usage
-----
    python scripts/verify_ha_entities.py --ha-url http://localhost:8123 --ha-token TOKEN

    # Or use env vars:
    HA_URL=http://localhost:8123 HA_TOKEN=abc python scripts/verify_ha_entities.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)


def _parse_dt(s: str) -> str:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        age_s = (datetime.now(timezone.utc) - dt).total_seconds()
        if age_s < 60:
            return f"{int(age_s)}s ago"
        if age_s < 3600:
            return f"{int(age_s/60)}m ago"
        return f"{int(age_s/3600)}h ago"
    except Exception:
        return s


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Starlink HA entities")
    parser.add_argument("--ha-url",   default=os.getenv("HA_URL",   "http://localhost:8123"))
    parser.add_argument("--ha-token", default=os.getenv("HA_TOKEN", ""))
    parser.add_argument("--filter",   default="starlink", help="Entity ID substring filter")
    args = parser.parse_args()

    if not args.ha_token:
        print("[ERROR] --ha-token required (or HA_TOKEN env var)")
        return 1

    headers = {"Authorization": f"Bearer {args.ha_token}"}
    r = requests.get(f"{args.ha_url}/api/states", headers=headers, timeout=10)
    if not r.ok:
        print(f"[ERROR] HA API returned {r.status_code}: {r.text[:200]}")
        return 1

    all_states = r.json()
    entities = [s for s in all_states if args.filter in s["entity_id"]]

    if not entities:
        print(f"[WARN] No entities matching {args.filter!r} found in HA.")
        print("  The integration may not be installed or configured yet.")
        return 0

    # Group by domain
    by_domain: dict[str, list] = {}
    for e in entities:
        domain = e["entity_id"].split(".")[0]
        by_domain.setdefault(domain, []).append(e)

    problems = []

    print(f"\n{'='*70}")
    print(f"  Starlink HA Entity Report — {len(entities)} entities")
    print(f"{'='*70}")

    for domain in sorted(by_domain):
        print(f"\n  [{domain.upper()}]")
        for e in sorted(by_domain[domain], key=lambda x: x["entity_id"]):
            state = e["state"]
            eid   = e["entity_id"]
            attrs = e.get("attributes", {})
            unit  = attrs.get("unit_of_measurement", "")
            age   = _parse_dt(e.get("last_changed", ""))
            status_icon = "✓" if state not in ("unavailable", "unknown") else "✗"

            if state in ("unavailable", "unknown"):
                problems.append(eid)

            val = f"{state} {unit}".strip()
            print(f"    {status_icon}  {eid:<55} {val:<20} ({age})")

    print(f"\n{'='*70}")
    if problems:
        print(f"  ⚠ {len(problems)} problematic entities:")
        for p in problems:
            print(f"    - {p}")
    else:
        print(f"  ✓ All {len(entities)} entities are reporting data")
    print(f"{'='*70}\n")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
