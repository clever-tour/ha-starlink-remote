import httpx
import logging
import sys
import os
from pathlib import Path

# Mock the directory structure for imports
pkg_path = str(Path(__file__).parent.parent / "custom_components" / "starlink_ha")
if pkg_path not in sys.path:
    sys.path.insert(0, pkg_path)

from spacex.api.device.device_pb2 import Request, GetStatusRequest

def main():
    cookie = os.environ.get("STARLINK_COOKIE")
    
    url = "https://api2.starlink.com/SpaceX.API.Device.Device/Handle"
    
    headers = {
        "accept": "*/*",
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "cookie": cookie,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    }

    # EMPTY target_id
    req = Request(get_status=GetStatusRequest())
    serialized = req.SerializeToString()
    frame = b'\x00' + len(serialized).to_bytes(4, 'big') + serialized
    
    print("[*] Calling GetStatus with EMPTY target_id...")
    try:
        with httpx.Client(http2=True) as client:
            resp = client.post(url, headers=headers, content=frame, timeout=10.0)
            print(f"[*] HTTP Status: {resp.status_code}")
            print(f"[*] Headers: {dict(resp.headers)}")
            
            grpc_status = resp.headers.get("grpc-status", "0")
            print(f"[*] gRPC Status: {grpc_status}")
            print(f"[*] gRPC Message: {resp.headers.get('grpc-message')}")
            
            # Print first 100 bytes of content in hex
            print(f"[*] Content (hex): {resp.content[:100].hex()}")
            
    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    main()
