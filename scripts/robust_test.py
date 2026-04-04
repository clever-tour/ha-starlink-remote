import httpx
import json
from pathlib import Path
from spacex.api.device.device_pb2 import Request, GetStatusRequest

def main():
    with open("cookie.txt", "r") as f:
        cookie_str = f.read().strip()
    
    url = "https://starlink.com/api/SpaceX.API.Device.Device/Handle"
    target_id = "Router-0100000000000000008B65AD"
    
    headers = {
        "accept": "*/*",
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "origin": "https://www.starlink.com",
        "referer": "https://www.starlink.com/"
    }
    
    # Manually parse cookies into a dict for httpx
    cookies = {}
    for part in cookie_str.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            cookies[k] = v

    req = Request(target_id=target_id, get_status=GetStatusRequest())
    serialized = req.SerializeToString()
    frame = b'\x00' + len(serialized).to_bytes(4, 'big') + serialized
    
    print(f"[*] Testing {target_id} with {len(cookies)} cookies...")
    
    with httpx.Client(http2=True, cookies=cookies) as client:
        resp = client.post(url, headers=headers, content=frame, timeout=10.0)
        print(f"[*] HTTP Status: {resp.status_code}")
        grpc_status = resp.headers.get("grpc-status", "0")
        print(f"[*] gRPC Status: {grpc_status}")
        if grpc_status == "0":
            print("[SUCCESS] Connected!")
        else:
            print(f"[-] gRPC Error: {resp.headers.get('grpc-message')}")
            # print(f"[*] Headers: {dict(resp.headers)}")

if __name__ == "__main__":
    main()
