import httpx
import json
import os
import sys
import time
import requests

def test_cookie(cookie):
    endpoints = [
        "https://starlink.com/api/SpaceX.API.Device.Device/Handle",
        "https://api2.starlink.com/SpaceX.API.Device.Device/Handle"
    ]
    target_id = "Router-0100000000000000008B65AD"
    headers = {
        "accept": "*/*",
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "cookie": cookie,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "origin": "https://starlink.com",
        "referer": "https://starlink.com/account/home"
    }
    
    from pathlib import Path
    pkg_path = str(Path(__file__).parent.parent / "custom_components" / "starlink_ha")
    if pkg_path not in sys.path:
        sys.path.insert(0, pkg_path)
    from spacex.api.device.device_pb2 import Request, GetStatusRequest
    req = Request(target_id=target_id, get_status=GetStatusRequest())
    serialized = req.SerializeToString()
    frame = b'\x00' + len(serialized).to_bytes(4, 'big') + serialized

    for url in endpoints:
        print(f"[*] Probing {url}...")
        try:
            with httpx.Client(http2=True) as client:
                resp = client.post(url, headers=headers, content=frame, timeout=10.0)
                print(f"[*] Probe HTTP: {resp.status_code}")
                print(f"[*] Probe gRPC Status: {resp.headers.get('grpc-status')}")
                if resp.status_code == 200 and resp.headers.get("grpc-status", "0") == "0":
                    return True
                else:
                    print(f"[*] Probe gRPC Message: {resp.headers.get('grpc-message')}")
        except Exception as e:
            print(f"[*] Probe Error: {e}")
    return False

def main():
    URL = "http://192.168.3.26:8123"
    TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIzNTA4MGMyZjNmMDQ0NmEzYWYxN2NhMmQ5ODEyNTY3YiIsImlhdCI6MTc3NTA0MjM4MSwiZXhwIjoyMDkwNDAyMzgxfQ.OufTnfuX_Fn22d7V3ffaVoc35DKl7zTvbi1pIw2vbzI"
    
    with open("cookie.txt", "r") as f:
        cookie = f.read().strip()
    
    print("[*] Verifying cookie against Starlink API...")
    if not test_cookie(cookie):
        print("[-] Cookie is invalid or expired. Please refresh it!")
        return

    print("[+] Cookie is working! Proceeding with HA setup...")
    
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    
    # Delete old ones
    r = requests.get(f"{URL}/api/config/config_entries/entry", headers=headers)
    for e in r.json():
        if e["domain"] == "starlink_ha":
            print(f"[*] Deleting old entry {e['entry_id']}...")
            requests.delete(f"{URL}/api/config/config_entries/entry/{e['entry_id']}", headers=headers)

    # Start flow
    r = requests.post(f"{URL}/api/config/config_entries/flow", headers=headers, json={"handler": "starlink_ha"})
    flow_id = r.json().get("flow_id")
    
    # Submit
    data = {
        "name": "Starlink-Final",
        "cookie": cookie,
        "router_id": "0100000000000000008B65AD",
        "skip_validation": False, # Try real validation first
        "cookie_dir": "/config/.starlink_cookies",
        "scan_interval": 60
    }
    r = requests.post(f"{URL}/api/config/config_entries/flow/{flow_id}", headers=headers, json=data)
    print(f"[+] Final Setup Response: {r.text}")

if __name__ == "__main__":
    main()
