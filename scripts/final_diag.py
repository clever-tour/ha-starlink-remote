import httpx
import json
import os
import sys
from pathlib import Path

# Mock the directory structure for imports
pkg_path = str(Path(__file__).parent.parent / "custom_components" / "starlink_ha")
if pkg_path not in sys.path:
    sys.path.insert(0, pkg_path)

from spacex.api.device.device_pb2 import Request, GetStatusRequest

def test_config(cookie, url, target_id):
    headers = {
        "accept": "*/*",
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "cookie": cookie,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "origin": "https://starlink.com",
        "referer": "https://starlink.com/account/home"
    }
    
    req = Request(target_id=target_id, get_status=GetStatusRequest())
    serialized = req.SerializeToString()
    frame = b'\x00' + len(serialized).to_bytes(4, 'big') + serialized
    
    print(f"[*] Testing {target_id} on {url}...")
    try:
        with httpx.Client(http2=True) as client:
            resp = client.post(url, headers=headers, content=frame, timeout=10.0)
            grpc_status = resp.headers.get("grpc-status", "0")
            if grpc_status == "0":
                print(f"[+] SUCCESS!")
                return True
            else:
                print(f"[-] gRPC Error {grpc_status}: {resp.headers.get('grpc-message')}")
                return False
    except Exception as e:
        print(f"[-] Error: {e}")
        return False

if __name__ == "__main__":
    with open("cookie.txt", "r") as f:
        COOKIE = f.read().strip()
    
    URLS = [
        "https://starlink.com/api/SpaceX.API.Device.Device/Handle",
        "https://api2.starlink.com/SpaceX.API.Device.Device/Handle"
    ]
    
    IDS = [
        "Router-0100000000000000008B65AD",
        "ut10588f9d-45017219-5815f472"
    ]
    
    for url in URLS:
        for tid in IDS:
            test_config(COOKIE, url, tid)
