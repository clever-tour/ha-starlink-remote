import httpx
import json
import os
import re
import time
from pathlib import Path

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'
COOKIE_FILE = "custom_components/starlink_ha/cookie.txt"
TARGET_ID = "0100000000000000008B65AD"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def test_persistence():
    if not os.path.exists(COOKIE_FILE):
        log(f"[-] {COOKIE_FILE} not found")
        return

    with open(COOKIE_FILE, "r") as f:
        cookie_str = f.read().strip()
    
    jar = httpx.Cookies()
    for part in cookie_str.split(';'):
        if '=' in part:
            k, v = part.strip().split('=', 1)
            jar.set(k, v, domain='.starlink.com')
    
    log(f"[*] Loaded cookies: {[c.name for c in jar.jar]}")
    
    client = httpx.Client(http2=True, cookies=jar, timeout=15.0, follow_redirects=True)
    
    # 1. Refresh Sequence (The starlink-client approach)
    log("[*] Step 1: Hitting dashboard to trigger session...")
    r1 = client.get("https://www.starlink.com/account/home", headers={'user-agent': UA})
    log(f"[+] Status: {r1.status_code}")
    
    log("[*] Step 2: Hitting service-lines to find XSRF-TOKEN...")
    r2 = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers={'user-agent': UA})
    log(f"[+] Status: {r2.status_code}")
    
    # Capture Set-Cookies
    xsrf = client.cookies.get('XSRF-TOKEN', '')
    if not xsrf:
        log("[!] XSRF-TOKEN not in cookies, checking HTML...")
        m = re.search(r'xsrfToken":"([^"]+)"', r1.text)
        if m:
            xsrf = m.group(1)
            log(f"[+] Found XSRF in HTML: {xsrf[:10]}...")
            client.cookies.set('XSRF-TOKEN', xsrf, domain='.starlink.com')
    else:
        log(f"[+] Found XSRF in Cookies: {xsrf[:10]}...")

    # 2. Test gRPC Call
    from google.protobuf.json_format import MessageToDict
    # Manual import path if needed
    import sys
    sys.path.insert(0, "custom_components/starlink_ha")
    from spacex.api.device.device_pb2 import Request, GetStatusRequest, Response

    req = Request(target_id=TARGET_ID, get_status=GetStatusRequest())
    ser = req.SerializeToString()
    frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
    
    headers = {
        'accept': '*/*', 
        'content-type': 'application/grpc-web+proto', 
        'x-grpc-web': '1', 
        'user-agent': UA, 
        'x-xsrf-token': xsrf
    }
    
    log(f"[*] Step 3: Attempting gRPC call to {TARGET_ID}...")
    r3 = client.post("https://api2.starlink.com/SpaceX.API.Device.Device/Handle", headers=headers, content=frame)
    log(f"[+] gRPC Status: {r3.status_code}")
    
    if r3.status_code == 200:
        if len(r3.content) > 5:
            out = Response()
            out.ParseFromString(r3.content[5:5+int.from_bytes(r3.content[1:5], 'big')])
            rt = out.WhichOneof('response')
            log(f"[SUCCESS] Received {rt}")
            if rt:
                log(f"[DATA] Keys: {list(MessageToDict(getattr(out, rt)).keys())}")
        else:
            log("[-] Response 200 but empty body")
    else:
        log(f"[-] Error Body: {r3.text[:200]}")

    # 3. Save Updated Cookies
    final_cookies = "; ".join([f"{c.name}={c.value}" for c in client.cookies.jar])
    log("[*] Final Cookie String length: " + str(len(final_cookies)))
    if xsrf in final_cookies:
        log("[+] XSRF-TOKEN is now present in the persistent string!")

if __name__ == "__main__":
    test_persistence()
