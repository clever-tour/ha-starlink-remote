import requests
import json
import os
import sys
import time

def setup_ha(url, token, cookie, router_id, name):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # 1. Start flow
    print(f"[*] Starting flow for {name}...")
    r = requests.post(f"{url}/api/config/config_entries/flow", headers=headers, json={"handler": "starlink_ha"})
    if not r.ok:
        print(f"[-] Failed to start flow: {r.text}")
        return
    
    flow_id = r.json().get("flow_id")
    print(f"[+] Flow ID: {flow_id}")
    
    # Step 1: Submit Cookie
    print(f"[*] Submitting Cookie...")
    r = requests.post(f"{url}/api/config/config_entries/flow/{flow_id}", headers=headers, json={"cookie": cookie})
    if not r.ok:
        print(f"[-] Failed to submit cookie: {r.text}")
        return
    
    # Step 2: Select Device (or handle immediate success if flow logic differs)
    resp_json = r.json()
    if resp_json.get("type") == "form" and resp_json.get("step_id") == "select_device":
        print("[*] Selecting device...")
        r = requests.post(f"{url}/api/config/config_entries/flow/{flow_id}", headers=headers, json={"device_id": router_id})
        if not r.ok:
            print(f"[-] Failed to select device: {r.text}")
            return
    
    print(f"[+] Final Response: {r.text}")
    
    # 3. Wait and check entities
    print("[*] Waiting for entities to appear...")
    time.sleep(15)
    r = requests.get(f"{url}/api/states", headers=headers)
    entities = [s["entity_id"] for s in r.json() if "starlink" in s["entity_id"]]
    print(f"[+] Found {len(entities)} Starlink entities:")
    for eid in sorted(entities):
        state = requests.get(f"{url}/api/states/{eid}", headers=headers).json().get("state")
        print(f"    {eid}: {state}")

if __name__ == "__main__":
    URL = "http://192.168.3.26:8123"
    TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIzNTA4MGMyZjNmMDQ0NmEzYWYxN2NhMmQ5ODEyNTY3YiIsImlhdCI6MTc3NTA0MjM4MSwiZXhwIjoyMDkwNDAyMzgxfQ.OufTnfuX_Fn22d7V3ffaVoc35DKl7zTvbi1pIw2vbzI"
    with open("cookie.txt", "r") as f:
        COOKIE = f.read().strip()
    
    ROUTER_ID = "0100000000000000008B65AD"
    
    # Delete old ones first
    requests.get(f"{URL}/api/config/config_entries/entry", headers={"Authorization": f"Bearer {TOKEN}"})
    # (assuming manual deletion or entry cleanup happened)
    
    setup_ha(URL, TOKEN, COOKIE, ROUTER_ID, "Starlink-Discovery")
