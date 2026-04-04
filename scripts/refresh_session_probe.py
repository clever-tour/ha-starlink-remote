import httpx
import json
from pathlib import Path
from spacex.api.device.device_pb2 import Request, GetStatusRequest
import re

def main():
    with open("cookie.txt", "r") as f:
        cookie_str = f.read().strip()
    
    # 1. Try to get a fresh session/XSRF token
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "cookie": cookie_str,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    }
    
    print("[*] Fetching account home to refresh session...")
    with httpx.Client() as client:
        resp = client.get("https://www.starlink.com/account/home", headers=headers, follow_redirects=True)
        print(f"[*] GET Response: {resp.status_code}")
        
        # Merge new cookies
        new_cookies = "; ".join([f"{k}={v}" for k, v in resp.cookies.items()])
        full_cookie = cookie_str
        if new_cookies:
            full_cookie += "; " + new_cookies
            print(f"[+] Added new cookies: {list(resp.cookies.keys())}")

        xsrf = resp.cookies.get("XSRF-TOKEN")
        if not xsrf:
            match = re.search(r'xsrfToken":"([^"]+)"', resp.text)
            if match:
                xsrf = match.group(1)
                print(f"[+] Found XSRF in HTML: {xsrf}")
        else:
            print(f"[+] Found XSRF in Cookie: {xsrf}")

    # 2. Try gRPC with full session
    url = "https://api2.starlink.com/SpaceX.API.Device.Device/Handle"
    target_id = "Router-0100000000000000008B65AD"
    
    headers = {
        "accept": "*/*",
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "cookie": full_cookie,
        "x-xsrf-token": xsrf if xsrf else "",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "origin": "https://www.starlink.com",
        "referer": "https://www.starlink.com/account/home"
    }
    
    from spacex.api.device.device_pb2 import GetStatusRequest
    req = Request(target_id=target_id, get_status=GetStatusRequest())
    serialized = req.SerializeToString()
    frame = b'\x00' + len(serialized).to_bytes(4, 'big') + serialized
    
    print(f"[*] Testing connection to {url}...")
    try:
        with httpx.Client(http2=True) as client:
            resp = client.post(url, headers=headers, content=frame, timeout=10.0)
            print(f"[*] POST Status: {resp.status_code}")
            print(f"[*] gRPC Status: {resp.headers.get('grpc-status')}")
            if resp.status_code == 200 and resp.headers.get("grpc-status") == "0":
                print("[SUCCESS] hand-shake verified")
            else:
                print(f"[-] Failed: {resp.headers.get('grpc-message')}")
    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    main()
