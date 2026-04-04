import httpx
import time as _time
import sys
import os
import json
from pathlib import Path
from google.protobuf.json_format import MessageToDict

# Add project root to sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "custom_components" / "starlink_ha"))

from spacex.api.device.device_pb2 import Request, GetStatusRequest, Response

STARLINK_API_URL = "https://starlink.com/api/SpaceX.API.Device.Device/Handle"

def _make_grpc_web_call(req_obj: Request, cookie: str) -> tuple[Response, dict]:
    """Execute a gRPC-Web call and return response + new cookies."""
    serialized = req_obj.SerializeToString()
    frame = b'\x00' + len(serialized).to_bytes(4, 'big') + serialized
    
    headers = {
        "accept": "*/*",
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "cookie": cookie,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "origin": "https://starlink.com",
        "referer": "https://starlink.com/account/home"
    }
    
    with httpx.Client(http2=True) as client:
        resp = client.post(STARLINK_API_URL, headers=headers, content=frame, timeout=15.0)
        
        if resp.status_code != 200:
            print(f"[-] HTTP Error {resp.status_code}")
            return None, {}
        
        # Capture new cookies
        new_cookies = {}
        for k, v in resp.cookies.items():
            new_cookies[k] = v

        if len(resp.content) < 5:
            return Response(), new_cookies
        
        data_len = int.from_bytes(resp.content[1:5], 'big')
        data_payload = resp.content[5:5+data_len]
        
        out = Response()
        out.ParseFromString(data_payload)
        return out, new_cookies

def main():
    cookie_file = "cookie.txt"
    with open(cookie_file, "r") as f:
        cookie = f.read().strip()
        
    router_id = "0100000000000000008B65AD"
    print(f"[*] Fetching status for Router ID: {router_id}")
    
    try:
        target_id = f"Router-{router_id}"
        req = Request(target_id=target_id, get_status=GetStatusRequest())
        resp, new_cookies = _make_grpc_web_call(req, cookie)
        
        if resp:
            print("[+] Success! Response received.")
            # print(json.dumps(MessageToDict(resp), indent=2))
            
            # Refresh cookie logic
            if new_cookies:
                print("[*] Refreshing cookie.txt with new cookies...")
                # Merge logic: parse original, update with new
                cookie_dict = {}
                for part in cookie.split(";"):
                    if "=" in part:
                        k, v = part.strip().split("=", 1)
                        cookie_dict[k] = v
                cookie_dict.update(new_cookies)
                new_cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
                
                with open(cookie_file, "w") as f:
                    f.write(new_cookie_str)
                print("[+] cookie.txt updated.")
        else:
            print("[-] Failed to get response.")
            
    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    main()
