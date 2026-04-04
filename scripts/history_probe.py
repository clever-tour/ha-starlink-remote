import httpx
import json
import os
import sys
from pathlib import Path
from google.protobuf.json_format import MessageToDict

# Mock the directory structure for imports
pkg_path = str(Path(__file__).parent.parent / "custom_components" / "starlink_ha")
if pkg_path not in sys.path:
    sys.path.insert(0, pkg_path)

from spacex.api.device.device_pb2 import Request, GetHistoryRequest, Response
from spacex.api.device import wifi_pb2

def _make_grpc_web_call(req_obj: Request, cookie: str, url: str) -> Response:
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
        resp = client.post(url, headers=headers, content=frame, timeout=15.0)
        
        grpc_status = resp.headers.get("grpc-status", "0")
        if grpc_status != "0":
            print(f"[-] gRPC Error {grpc_status} on {url}: {resp.headers.get('grpc-message')}")
            return None
        
        if len(resp.content) < 5:
            return Response()
        
        data_len = int.from_bytes(resp.content[1:5], 'big')
        data_payload = resp.content[5:5+data_len]
        
        out = Response()
        out.ParseFromString(data_payload)
        return out

def main():
    with open("cookie.txt", "r") as f:
        cookie = f.read().strip()
    
    target_id = "Router-0100000000000000008B65AD"
    urls = [
        "https://starlink.com/api/SpaceX.API.Device.Device/Handle",
        "https://api2.starlink.com/SpaceX.API.Device.Device/Handle"
    ]
    
    results = {}
    
    for url in urls:
        print(f"[*] Testing HISTORY on {url}...")
        
        # Try Dish History
        req_dish = Request(target_id=target_id, get_history=GetHistoryRequest())
        resp_dish = _make_grpc_web_call(req_dish, cookie, url)
        if resp_dish and resp_dish.HasField("dish_get_history"):
            print(f"[+] Found Dish History on {url}")
            results[f"DISH_HISTORY_{url}"] = MessageToDict(resp_dish.dish_get_history)
            
        # Try WiFi History
        # Note: Based on previous grep, it might be wifi_get_history in Response
        # but WifiGetHistoryRequest was not found in wifi_pb2.
        # Let's check the Response fields for history.
        if resp_dish and resp_dish.HasField("wifi_get_history"):
             print(f"[+] Found WiFi History on {url} via standard request")
             results[f"WIFI_HISTORY_{url}"] = MessageToDict(resp_dish.wifi_get_history)

    with open("scripts/history_probe.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\n[!] Results saved to scripts/history_probe.json")

if __name__ == "__main__":
    main()
