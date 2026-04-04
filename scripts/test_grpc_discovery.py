import httpx
import time as _time
import sys
import os
from pathlib import Path
from google.protobuf.json_format import MessageToDict

# Add project root to sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "custom_components" / "starlink_ha"))

from spacex.api.device.device_pb2 import Request, GetStatusRequest, GetHistoryRequest, Response

STARLINK_API_URL = "https://starlink.com/api/SpaceX.API.Device.Device/Handle"

def _make_grpc_web_call(req_obj: Request, cookie: str) -> Response:
    """Execute a gRPC-Web call."""
    # Wrap in gRPC-Web binary frame
    serialized = req_obj.SerializeToString()
    frame = b'\x00' + len(serialized).to_bytes(4, 'big') + serialized
    
    headers = {
        "accept": "*/*",
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "cookie": cookie,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "origin": "https://starlink.com",
        "referer": "https://starlink.com/account/home"
    }
    
    with httpx.Client(http2=True) as client:
        resp = client.post(STARLINK_API_URL, headers=headers, content=frame, timeout=15.0)
        
        if resp.status_code != 200:
            print(f"[-] HTTP Error {resp.status_code}: {resp.text[:200]}")
            raise Exception(f"HTTP Error {resp.status_code}")
        
        # Check gRPC status in headers
        grpc_status = resp.headers.get("grpc-status", "0")
        if grpc_status != "0":
            grpc_msg = resp.headers.get("grpc-message", "Unknown error")
            print(f"[-] gRPC Error {grpc_status}: {grpc_msg}")
            raise Exception(f"gRPC Error {grpc_status}: {grpc_msg}")
        
        # Parse response frame
        if len(resp.content) < 5:
            return Response()
        
        data_len = int.from_bytes(resp.content[1:5], 'big')
        data_payload = resp.content[5:5+data_len]
        
        out = Response()
        out.ParseFromString(data_payload)
        return out

def main():
    cookie = os.environ.get("STARLINK_COOKIE")
    if not cookie:
        print("[-] STARLINK_COOKIE not set")
        return

    # To discover devices, we usually call GetStatus with an empty target_id or a special target_id
    # But usually, there is a specific request for listing devices.
    # In some versions of the API, any request with a valid cookie might return device info in headers or trailers,
    # or we might need to use the 'web-inventory' API which we already tried.
    
    # Let's try to call GetStatusRequest with an empty target_id just to see what happens.
    print("[*] Attempting GetStatus with empty target_id...")
    try:
        req = Request(get_status=GetStatusRequest())
        resp = _make_grpc_web_call(req, cookie)
        print("[+] Success calling gRPC API!")
        print(MessageToDict(resp))
    except Exception as e:
        print(f"[-] gRPC Call failed: {e}")

if __name__ == "__main__":
    main()
