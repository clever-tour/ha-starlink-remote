import httpx
import logging
import sys
import os
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.DEBUG)
_LOGGER = logging.getLogger(__name__)

# Mock the directory structure for imports
pkg_path = str(Path(__file__).parent.parent / "custom_components" / "starlink_ha")
if pkg_path not in sys.path:
    sys.path.insert(0, pkg_path)

from spacex.api.device.device_pb2 import Request, GetStatusRequest
from const import STARLINK_API_URL

def _test_target(cookie_val, target_id):
    print(f"\n[*] Testing Target ID: {target_id}")
    
    # 1. Build Protobuf request
    req = Request(target_id=target_id, get_status=GetStatusRequest())
    serialized = req.SerializeToString()
    frame = b'\x00' + len(serialized).to_bytes(4, 'big') + serialized
    
    # 2. Headers
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "cookie": cookie_val,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "origin": "https://www.starlink.com",
        "referer": "https://www.starlink.com/"
    }

    # 3. Make raw call
    try:
        with httpx.Client(http2=True) as client:
            resp = client.post(STARLINK_API_URL, headers=headers, content=frame, timeout=10.0)
            
            if resp.status_code != 200:
                print(f"[-] HTTP Error {resp.status_code}")
                return False
            
            grpc_status = resp.headers.get("grpc-status", "0")
            if grpc_status != "0":
                grpc_msg = resp.headers.get("grpc-message", "Unknown")
                print(f"[-] gRPC Error {grpc_status}: {grpc_msg}")
                return False
                
            print(f"[+] SUCCESS for {target_id}!")
            return True
    except Exception as err:
        print(f"[-] Connection failed: {err}")
        return False

if __name__ == "__main__":
    cookie = os.environ.get("STARLINK_COOKIE")
    
    # Try multiple variations
    ids = [
        "0100000000000000008B65AD",
        "Router-0100000000000000008B65AD",
        "10588f9d-45017219-5815f472",
        "ut10588f9d-45017219-5815f472"
    ]
    
    for tid in ids:
        if _test_target(cookie, tid):
            print(f"\n[!!!] USE THIS ID: {tid}")
