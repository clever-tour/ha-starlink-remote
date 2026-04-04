import httpx
import json
import os
import sys
from pathlib import Path

# Mock the directory structure for imports
pkg_path = str(Path(__file__).parent.parent / "custom_components" / "starlink_ha")
if pkg_path not in sys.path:
    sys.path.insert(0, pkg_path)

from spacex.api.device.device_pb2 import Request, GetStatusRequest

def test_id(client, url, headers, tid):
    req = Request(target_id=tid, get_status=GetStatusRequest())
    serialized = req.SerializeToString()
    frame = b'\x00' + len(serialized).to_bytes(4, 'big') + serialized
    
    try:
        resp = client.post(url, headers=headers, content=frame, timeout=5.0)
        grpc_status = resp.headers.get("grpc-status", "0")
        if grpc_status == "0":
            return True, None
        return False, f"gRPC {grpc_status}: {resp.headers.get('grpc-message')}"
    except Exception as e:
        return False, str(e)

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

    ids_to_try = [
        "0100000000000000008B65AD",
        "Router-0100000000000000008B65AD",
        "ut0100000000000000008B65AD",
        "10588f9d-45017219-5815f472",
        "ut10588f9d-45017219-5815f472",
        "ACC-5147187-41313-10",
        "5147187"
    ]

    with httpx.Client(http2=True) as client:
        for tid in ids_to_try:
            print(f"[*] Trying {tid}...", end=" ", flush=True)
            ok, err = test_id(client, url, headers, tid)
            if ok:
                print("SUCCESS!")
                print(f"\n[!!!] FOUND WORKING ID: {tid}")
                return
            else:
                print(f"Failed ({err})")

if __name__ == "__main__":
    main()
