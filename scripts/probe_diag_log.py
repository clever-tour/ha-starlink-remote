import httpx
import json
import sys
from pathlib import Path
from google.protobuf.json_format import MessageToDict

# Add components path for imports
pkg_path = str(Path(__file__).parent.parent / "custom_components" / "starlink_ha")
if pkg_path not in sys.path:
    sys.path.insert(0, pkg_path)

from spacex.api.device.device_pb2 import Request, GetLogRequest, GetDiagnosticsRequest, Response

def _make_grpc_web_call(req_obj: Request, cookie: str, url: str) -> Response:
    serialized = req_obj.SerializeToString()
    frame = b'\x00' + len(serialized).to_bytes(4, 'big') + serialized
    headers = {
        "accept": "*/*",
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "cookie": cookie,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    }
    with httpx.Client(http2=True) as client:
        resp = client.post(url, headers=headers, content=frame, timeout=15.0)
        if resp.status_code != 200: return None
        if len(resp.content) < 5: return Response()
        data_len = int.from_bytes(resp.content[1:5], 'big')
        out = Response()
        out.ParseFromString(resp.content[5:5+data_len])
        return out

def main():
    with open("cookie.txt", "r") as f:
        cookie = f.read().strip()
    
    dish_id = "ut10588f9d-45017219-5815f472"
    url = "https://api2.starlink.com/SpaceX.API.Device.Device/Handle"
    
    results = {}
    
    # 1. Probe Diagnostics
    print(f"[*] Probing Diagnostics for: {dish_id}")
    req_diag = Request(target_id=dish_id, get_diagnostics=GetDiagnosticsRequest())
    resp_diag = _make_grpc_web_call(req_diag, cookie, url)
    if resp_diag:
        print("[+] Captured Diagnostics.")
        results["diagnostics"] = MessageToDict(resp_diag, always_print_fields_with_no_presence=True)
        
    # 2. Probe Log
    print(f"[*] Probing Log for: {dish_id}")
    req_log = Request(target_id=dish_id, get_log=GetLogRequest())
    resp_log = _make_grpc_web_call(req_log, cookie, url)
    if resp_log:
        print("[+] Captured Log.")
        results["log"] = MessageToDict(resp_log, always_print_fields_with_no_presence=True)

    with open("scripts/dish_diag_log_probe.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\n[!] Results saved to scripts/dish_diag_log_probe.json")

if __name__ == "__main__":
    main()
