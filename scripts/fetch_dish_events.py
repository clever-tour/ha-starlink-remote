import httpx, re, json, sys, os, binascii
from pathlib import Path
from google.protobuf.json_format import MessageToDict

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "starlink_remote"))

from spacex.api.device.device_pb2 import Request, GetStatusRequest, GetHistoryRequest, Response

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run():
    with open("cookie.txt", "r") as f: raw_cookie = f.read().strip()
    client = httpx.Client(http2=True, follow_redirects=True)
    
    print("[*] Priming Session...")
    r_prime = client.get("https://www.starlink.com/account/home", headers={"User-Agent": UA, "cookie": raw_cookie})
    print(f"  Prime Status: {r_prime.status_code}")
    
    fresh_cookie = "; ".join([f"{c.name}={c.value}" for c in client.cookies.jar])
    xsrf = client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')

    headers = {
        "User-Agent": UA, "cookie": fresh_cookie or raw_cookie, "x-xsrf-token": xsrf,
        "content-type": "application/grpc-web+proto", "x-grpc-web": "1"
    }
    url = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"
    tid = "ut10588f9d-45017219-5815f472"

    print(f"[*] Fetching Events for Dish: {tid}")
    
    # 1. REBOOTS
    req = Request(target_id=tid, get_status=GetStatusRequest())
    res = client.post(url, headers=headers, content=b'\x00' + len(req.SerializeToString()).to_bytes(4, 'big') + req.SerializeToString())
    print(f"  Status Req: {res.status_code} | Len: {len(res.content)}")
    if len(res.content) > 5:
        msg_len = int.from_bytes(res.content[1:5], 'big')
        out = Response()
        out.ParseFromString(res.content[5:5+msg_len])
        rt = out.WhichOneof('response')
        print(f"  Received Response Type: {rt}")
        if rt == 'dish_get_status':
            d = MessageToDict(out.dish_get_status, preserving_proto_field_name=True)
            print(f"\n[REBOOT DATA]\n  - Boot Count: {d.get('device_info', {}).get('bootcount')}\n  - Uptime: {d.get('device_state', {}).get('uptime_s')}s")

    # 2. SEARCHING / OUTAGES
    req = Request(target_id=tid, get_history=GetHistoryRequest())
    res = client.post(url, headers=headers, content=b'\x00' + len(req.SerializeToString()).to_bytes(4, 'big') + req.SerializeToString())
    print(f"  History Req: {res.status_code} | Len: {len(res.content)}")
    if len(res.content) > 5:
        msg_len = int.from_bytes(res.content[1:5], 'big')
        out = Response()
        out.ParseFromString(res.content[5:5+msg_len])
        rt = out.WhichOneof('response')
        print(f"  Received Response Type: {rt}")
        if rt == 'dish_get_history':
            d = MessageToDict(out.dish_get_history, preserving_proto_field_name=True)
            print("\n[SEARCHING / OUTAGE EVENTS]")
            outages = d.get('outages', [])
            if not outages: print("  - No outages in history.")
            for o in outages[-10:]:
                print(f"  - Cause: {o.get('cause', 'UNKNOWN'):15} | Duration: {int(o.get('duration_ns', 0))/1e9:6.2f}s")

if __name__ == "__main__": run()
