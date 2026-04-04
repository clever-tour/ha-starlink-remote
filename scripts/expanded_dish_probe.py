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
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
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
    
    # IDs to test
    targets = [
        "ut10588f9d-45017219-5815f472",
        "0100000000000000008B65AD"
    ]
    url = "https://api2.starlink.com/SpaceX.API.Device.Device/Handle"
    
    results = {}
    for target_id in targets:
        print(f"[*] Probing ID: {target_id}")
        req = Request(target_id=target_id, get_status=GetStatusRequest())
        resp = _make_grpc_web_call(req, cookie, url)
        
        if resp:
            if resp.HasField("dish_get_status"):
                print(f"[+] SUCCESS: Found Dish Status on {target_id}")
                results[target_id] = MessageToDict(resp.dish_get_status)
            elif resp.HasField("wifi_get_status"):
                print(f"[+] INFO: Found WiFi Status on {target_id}")
                # Check for hidden dish data in wifi status
                results[target_id + "_wifi"] = MessageToDict(resp.wifi_get_status)
        else:
            print(f"[-] FAILED: No response for {target_id}")

    with open("scripts/dish_probe_v2.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\n[!] Results saved to scripts/dish_probe_v2.json")

if __name__ == "__main__":
    main()
