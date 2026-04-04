import httpx
import logging
import sys
import os
import re
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)

# Mock the directory structure for imports
pkg_path = str(Path(__file__).parent.parent / "custom_components" / "starlink_ha")
if pkg_path not in sys.path:
    sys.path.insert(0, pkg_path)

from spacex.api.device.device_pb2 import Request, GetStatusRequest

def _get_xsrf_token(cookie_str):
    print("[*] Fetching XSRF token...")
    headers = {
        "cookie": cookie_str,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    }
    with httpx.Client() as client:
        resp = client.get("https://www.starlink.com/account/home", headers=headers)
        print(f"[*] GET Response: {resp.status_code}")
        xsrf = resp.cookies.get("XSRF-TOKEN")
        if xsrf:
            print(f"[+] Found XSRF token in cookies: {xsrf}")
            return xsrf, "; ".join([f"{k}={v}" for k, v in resp.cookies.items()])
        
        # Try to find it in the HTML
        match = re.search(r'xsrfToken":"([^"]+)"', resp.text)
        if match:
            print(f"[+] Found XSRF token in HTML: {match.group(1)}")
            return match.group(1), ""
            
    print("[-] XSRF token not found")
    return None, ""

def _test_with_xsrf(cookie_str, target_id):
    xsrf, extra_cookies = _get_xsrf_token(cookie_str)
    full_cookie = cookie_str
    if extra_cookies:
        full_cookie += "; " + extra_cookies
        
    print(f"[*] Testing with XSRF: {xsrf}")
    
    url = "https://api2.starlink.com/SpaceX.API.Device.Device/Handle"
    
    headers = {
        "accept": "*/*",
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "cookie": full_cookie,
        "x-xsrf-token": xsrf if xsrf else "",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "origin": "https://www.starlink.com",
        "referer": "https://www.starlink.com/"
    }

    req = Request(target_id=target_id, get_status=GetStatusRequest())
    serialized = req.SerializeToString()
    frame = b'\x00' + len(serialized).to_bytes(4, 'big') + serialized
    
    try:
        with httpx.Client(http2=True) as client:
            resp = client.post(url, headers=headers, content=frame, timeout=10.0)
            print(f"[*] POST Response: {resp.status_code}")
            grpc_status = resp.headers.get("grpc-status", "0")
            print(f"[*] gRPC Status: {grpc_status}")
            if grpc_status == "0":
                print("[SUCCESS] Connected!")
            else:
                print(f"[-] gRPC Error: {resp.headers.get('grpc-message')}")
    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    cookie = os.environ.get("STARLINK_COOKIE")
    target = "ut10588f9d-45017219-5815f472"
    _test_with_xsrf(cookie, target)
