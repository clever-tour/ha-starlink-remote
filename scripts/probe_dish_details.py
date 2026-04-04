import httpx
import json
import sys
from pathlib import Path
from google.protobuf.json_format import MessageToDict

# Add components path for imports
pkg_path = str(Path(__file__).parent.parent / "custom_components" / "starlink_ha")
if pkg_path not in sys.path:
    sys.path.insert(0, pkg_path)

from spacex.api.device.device_pb2 import Request, GetStatusRequest, Response

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
        if resp.status_code != 200: return None
        if len(resp.content) < 5: return Response()
        data_len = int.from_bytes(resp.content[1:5], 'big')
        data_payload = resp.content[5:5+data_len]
        out = Response()
        out.ParseFromString(data_payload)
        return out

def main():
    with open("cookie.txt", "r") as f:
        cookie = f.read().strip()
    
    # Dish ID (User Terminal)
    dish_id = "ut10588f9d-45017219-5815f472"
    url = "https://api2.starlink.com/SpaceX.API.Device.Device/Handle"
    
    print(f"[*] Probing Dish ID: {dish_id}")
    req = Request(target_id=dish_id, get_status=GetStatusRequest())
    resp = _make_grpc_web_call(req, cookie, url)
    
    if resp and resp.HasField("dish_get_status"):
        print("[+] Success! Captured Dish Status.")
        data = MessageToDict(resp.dish_get_status)
        
        # Look for the specific fields
        metrics = {
            "alerts": data.get("alerts"),
            "obstruction_stats": data.get("obstructionStats"),
            "alignment_stats": data.get("alignmentStats"),
            "dish_state": data.get("state")
        }
        print(json.dumps(metrics, indent=2))
        
        with open("scripts/dish_probe.json", "w") as f:
            json.dump(data, f, indent=2)
    else:
        print("[-] Failed to get dish_get_status response.")

if __name__ == "__main__":
    main()
