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

from spacex.api.device.device_pb2 import (
    Request, GetStatusRequest, GetHistoryRequest, GetDeviceInfoRequest,
    GetLocationRequest, GetDiagnosticsRequest, GetPersistentStatsRequest,
    Response
)
from spacex.api.device import wifi_pb2

def _make_grpc_web_call(req_obj: Request, cookie: str) -> Response:
    url = "https://starlink.com/api/SpaceX.API.Device.Device/Handle"
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
        
        if resp.status_code != 200:
            print(f"[-] HTTP Error {resp.status_code}")
            return None
        
        grpc_status = resp.headers.get("grpc-status", "0")
        if grpc_status != "0":
            print(f"[-] gRPC Error {grpc_status}: {resp.headers.get('grpc-message')}")
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
    
    # List of requests to try
    probes = {
        "DEVICE_INFO": GetDeviceInfoRequest(),
        "LOCATION": GetLocationRequest(),
        "DIAGNOSTICS": GetDiagnosticsRequest(),
        "PERSISTENT_STATS": GetPersistentStatsRequest(),
        "WIFI_CLIENTS": wifi_pb2.WifiGetClientsRequest(),
        "WIFI_CLIENT_HISTORY": wifi_pb2.WifiGetClientHistoryRequest(),
        "WIFI_PING_METRICS": wifi_pb2.WifiGetPingMetricsRequest(),
    }
    
    results = {}
    
    for label, sub_req in probes.items():
        print(f"[*] Probing {label}...")
        req = Request(target_id=target_id)
        if label == "PERSISTENT_STATS":
            req.get_persistent_stats.CopyFrom(sub_req)
        elif label == "DEVICE_INFO":
            req.get_device_info.CopyFrom(sub_req)
        elif label == "LOCATION":
            req.get_location.CopyFrom(sub_req)
        elif label == "DIAGNOSTICS":
            req.get_diagnostics.CopyFrom(sub_req)
        elif label == "WIFI_CLIENTS":
            req.wifi_get_clients.CopyFrom(sub_req)
        elif label == "WIFI_CLIENT_HISTORY":
            req.wifi_get_client_history.CopyFrom(sub_req)
        elif label == "WIFI_PING_METRICS":
            req.wifi_get_ping_metrics.CopyFrom(sub_req)
            
        resp = _make_grpc_web_call(req, cookie)
        if resp:
            results[label] = MessageToDict(resp, always_print_fields_with_no_presence=True)
            print(f"[+] Success for {label}")
        else:
            print(f"[-] Failed for {label}")

    # Webagg Account Probe
    print("[*] Probing Webagg Account...")
    try:
        headers = {
            "cookie": cookie,
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        }
        # Accounts
        resp = httpx.get("https://api.starlink.com/webagg/v2/accounts", headers=headers, timeout=10.0)
        if resp.status_code == 200:
            results["WEB_ACCOUNTS"] = resp.json()
            print("[+] Success for WEB_ACCOUNTS")
        else:
            print(f"[-] Failed for WEB_ACCOUNTS: {resp.status_code}")
            
        # Service Lines
        resp = httpx.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=headers, timeout=10.0)
        if resp.status_code == 200:
            results["WEB_SERVICE_LINES"] = resp.json()
            print("[+] Success for WEB_SERVICE_LINES")
            
    except Exception as e:
        print(f"[-] Error for Webagg: {e}")

    with open("scripts/probe_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\n[!] Results saved to scripts/probe_results.json")

if __name__ == "__main__":
    main()
