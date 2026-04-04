import os
import httpx
import re
import json
import time
from google.protobuf.json_format import MessageToDict

import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "starlink_remote"))

try:
    from spacex.api.device.device_pb2 import Request, GetStatusRequest, Response
except ImportError:
    print("[-] Error: Could not import protobuf definitions.")
    sys.exit(1)

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36'

def test_telemetry():
    cookie_path = "cookie.txt"
    if not os.path.exists(cookie_path):
        print(f"[-] Error: {cookie_path} not found")
        return

    with open(cookie_path, "r") as f:
        cookie_str = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    
    # Discovery
    print("[*] Using hardware IDs from previous success...")
    discovered_ids = ["Router-0100000000000000008B65AD", "ut10588f9d-45017219-5815f472"]

    # Extract XSRF token
    xsrf_token = ""
    xsrf_match = re.search(r'XSRF-TOKEN=([^;]+)', cookie_str)
    if xsrf_match:
        xsrf_token = xsrf_match.group(1)
        print(f"[*] Found XSRF Token: {xsrf_token[:10]}...")

    def make_grpc_call(tid, req_obj, url):
        ser = req_obj.SerializeToString()
        frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
        
        grpc_headers = {
            'accept': '*/*', 
            'content-type': 'application/grpc-web+proto', 
            'x-grpc-web': '1', 
            'user-agent': UA, 
            'cookie': cookie_str, 
            'origin': 'https://starlink.com',
            'referer': 'https://starlink.com/account/home'
        }
        if xsrf_token:
            grpc_headers['x-xsrf-token'] = xsrf_token

        try:
            res = client.post(url, headers=grpc_headers, content=frame, timeout=10.0)
            print(f"  [POLL] {tid} -> {url} Status: {res.status_code} Content-Len: {len(res.content)}")
            
            if res.status_code == 200 and len(res.content) > 5:
                out = Response()
                msg_len = int.from_bytes(res.content[1:5], 'big')
                out.ParseFromString(res.content[5:5+msg_len])
                return out
        except Exception as e:
            print(f"    [-] Error: {e}")
        return None

    # Test both endpoints
    endpoints = [
        "https://api2.starlink.com/SpaceX.API.Device.Device/Handle",
        "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"
    ]

    for url in endpoints:
        print(f"\n--- Testing ENDPOINT: {url} ---")
        for tid in discovered_ids:
            print(f"[*] Polling {tid}...")
            resp = make_grpc_call(tid, Request(target_id=tid, get_status=GetStatusRequest()), url)
            if resp:
                rt = resp.WhichOneof('response')
                if rt:
                    rd = MessageToDict(getattr(resp, rt), preserving_proto_field_name=True)
                    print(f"  [+] SUCCESS: {rt} received.")
                    if rt == 'dish_get_status':
                        print(f"    - Uptime: {rd.get('device_state', {}).get('uptime_s')}s")
                        print(f"    - Alignment: Azimuth {rd.get('boresight_azimuth_deg')}")
                else: print("  [-] Empty response.")
            else: print("  [-] Call failed.")

if __name__ == "__main__":
    test_telemetry()
