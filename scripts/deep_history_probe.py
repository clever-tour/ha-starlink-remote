import httpx
import json
import sys
from pathlib import Path
from google.protobuf.json_format import MessageToDict

# Add components path for imports
pkg_path = str(Path(__file__).parent.parent / "custom_components" / "starlink_ha")
if pkg_path not in sys.path:
    sys.path.insert(0, pkg_path)

from spacex.api.device.device_pb2 import Request, GetHistoryRequest, Response

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
    
    # Target Dish ID for deep history
    dish_id = "ut10588f9d-45017219-5815f472"
    url = "https://api2.starlink.com/SpaceX.API.Device.Device/Handle"
    
    print(f"[*] Fetching FULL History for: {dish_id}")
    req = Request(target_id=dish_id, get_history=GetHistoryRequest())
    resp = _make_grpc_web_call(req, cookie, url)
    
    if resp and resp.HasField("dish_get_history"):
        print("[+] Success! Captured History.")
        # ALWAYS print fields with no presence to see everything
        data = MessageToDict(resp.dish_get_history, always_print_fields_with_no_presence=True)
        
        # Check for outages
        history_obj = data.get("history", data)
        outages = history_obj.get("outages", [])
        print(f"[!] Found {len(outages)} outage events in the buffer.")
        
        if outages:
            print("[*] Sample Outage Event:")
            print(json.dumps(outages[0], indent=2))
        
        with open("scripts/full_history_dump.json", "w") as f:
            json.dump(data, f, indent=2)
    else:
        print("[-] Failed to get dish_get_history response.")

if __name__ == "__main__":
    main()
