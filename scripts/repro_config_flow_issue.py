import httpx
import logging
import sys
import os
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.DEBUG)
_LOGGER = logging.getLogger(__name__)

# Mock the directory structure for imports
custom_path = str(Path(__file__).parent.parent / "custom_components" / "starlink_ha")
if custom_path not in sys.path:
    sys.path.insert(0, custom_path)

from spacex.api.device.device_pb2 import Request, GetStatusRequest
from const import STARLINK_API_URL

def _check_connection(cookie_val, router_id) -> None:
    _LOGGER.debug("[CHECK] Testing connection for %s", router_id)

    # 1. Build Protobuf request
    req = Request(target_id=router_id, get_status=GetStatusRequest())
    serialized = req.SerializeToString()
    frame = b'\x00' + len(serialized).to_bytes(4, 'big') + serialized
    
    # 2. Headers
    headers = {
        "accept": "*/*",
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "cookie": cookie_val,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "origin": "https://starlink.com",
        "referer": "https://starlink.com/account/home"
    }

    # 3. Make raw call
    try:
        with httpx.Client(http2=True) as client:
            resp = client.post(STARLINK_API_URL, headers=headers, content=frame, timeout=10.0)
            
            _LOGGER.debug("[CHECK] HTTP %d received", resp.status_code)
            
            if resp.status_code != 200:
                _LOGGER.warning("[CHECK] HTTP Error %d: %s", resp.status_code, resp.text[:200])
                raise Exception(f"HTTP {resp.status_code}")
            
            grpc_status = resp.headers.get("grpc-status", "0")
            if grpc_status != "0":
                grpc_msg = resp.headers.get("grpc-message", "Unknown")
                _LOGGER.warning("[CHECK] gRPC Error %s: %s", grpc_status, grpc_msg)
                raise Exception(f"gRPC {grpc_status}: {grpc_msg}")
                
            _LOGGER.info("[CHECK] Connection successful for %s", router_id)
    except Exception as err:
        _LOGGER.error("[CHECK] Connection failed: %s", err)
        raise

if __name__ == "__main__":
    cookie = os.environ.get("STARLINK_COOKIE")
    # WITHOUT PREFIX - this is what config_flow.py does if user pastes raw ID
    router_id = "0100000000000000008B65AD" 
    
    print(f"[*] Testing WITHOUT prefix: {router_id}")
    try:
        _check_connection(cookie, router_id)
        print("[+] SUCCESS (unexpectedly worked without prefix)")
    except Exception as e:
        print(f"[-] FAILED as expected: {e}")

    # WITH PREFIX
    router_id_with_prefix = f"Router-{router_id}"
    print(f"\n[*] Testing WITH prefix: {router_id_with_prefix}")
    try:
        _check_connection(cookie, router_id_with_prefix)
        print("[+] SUCCESS with prefix")
    except Exception as e:
        print(f"[-] FAILED even with prefix: {e}")
