import httpx
import json
import time
import sys
import re
from pathlib import Path
from google.protobuf.json_format import MessageToDict

# Add components path
pkg_path = str(Path(__file__).parent.parent / "custom_components" / "starlink_ha")
if pkg_path not in sys.path:
    sys.path.insert(0, pkg_path)

from spacex.api.device.device_pb2 import Request, GetStatusRequest, Response

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def test():
    with open("cookie.txt", "r") as f:
        cookie_str = f.read().strip()
    
    jar = httpx.Cookies()
    for part in cookie_str.split(';'):
        if '=' in part:
            k, v = part.strip().split('=', 1)
            jar.set(k, v, domain='.starlink.com')
    
    client = httpx.Client(http2=True, cookies=jar, timeout=15.0)
    
    print("[*] Fetching XSRF from /account/home...")
    resp = client.get("https://www.starlink.com/account/home", headers={'user-agent': UA})
    print(f"[*] GET Response: {resp.status_code}")
    
    xsrf = client.cookies.get('XSRF-TOKEN', '')
    if not xsrf:
        match = re.search(r'xsrfToken":"([^"]+)"', resp.text)
        if match:
            xsrf = match.group(1)
            print(f"[+] Found XSRF in HTML: {xsrf}")
            # Add it back to jar so it persists
            client.cookies.set('XSRF-TOKEN', xsrf, domain='.starlink.com')
    else:
        print(f"[+] Found XSRF in Cookies: {xsrf}")

    def _make_call(req_obj, url, current_xsrf):
        ser = req_obj.SerializeToString()
        frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
        headers = {
            'accept': '*/*', 'content-type': 'application/grpc-web+proto', 'x-grpc-web': '1', #
            'user-agent': UA, 
            'origin': 'https://www.starlink.com',
            'referer': 'https://www.starlink.com/account/home'
        }
        res = client.post(url, headers=headers, content=frame)
        print(f"[*] POST {url} -> {res.status_code}")
        if res.status_code != 200:
            return None
        
        if len(res.content) < 5:
            return None
            
        out = Response()
        out.ParseFromString(res.content[5:5+int.from_bytes(res.content[1:5], 'big')])
        return out

    # Poll Router
    rid = "Router-0100000000000000008B65AD"
    print(f"[*] Polling Router: {rid}")
    resp = _make_call(Request(target_id=rid, get_status=GetStatusRequest()), "https://api2.starlink.com/SpaceX.API.Device.Device/Handle", xsrf)
    if resp:
        print(f"[+] Router Response Type: {resp.WhichOneof('response')}")
        if resp.HasField('wifi_get_status'):
            print(f"[+] WiFi Status Keys: {list(MessageToDict(resp.wifi_get_status).keys())}")
    
    # Poll Dish
    did = "ut10588f9d-45017219-5815f472"
    print(f"[*] Polling Dish: {did}")
    resp = _make_call(Request(target_id=did, get_status=GetStatusRequest()), "https://api2.starlink.com/SpaceX.API.Device.Device/Handle", xsrf)
    if resp:
        print(f"[+] Dish Response Type: {resp.WhichOneof('response')}")
        if resp.HasField('dish_get_status'):
            print(f"[+] Dish Status Keys: {list(MessageToDict(resp.dish_get_status).keys())}")

if __name__ == "__main__":
    test()
