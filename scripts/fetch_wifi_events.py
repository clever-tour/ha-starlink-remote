import httpx, re, json, sys, os, binascii
from pathlib import Path
from google.protobuf.json_format import MessageToDict

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "starlink_remote"))

from spacex.api.device.device_pb2 import Request, GetStatusRequest, GetHistoryRequest, Response
from spacex.api.device.wifi_pb2 import WifiGetClientsRequest

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run():
    with open("cookie.txt", "r") as f: raw_cookie = f.read().strip()
    client = httpx.Client(http2=True, follow_redirects=True)
    
    print("[*] Priming Session...")
    client.get("https://www.starlink.com/account/home", headers={"User-Agent": UA, "cookie": raw_cookie})
    fresh_cookie = "; ".join([f"{c.name}={c.value}" for c in client.cookies.jar])
    xsrf = client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')

    headers = {
        "User-Agent": UA, "cookie": fresh_cookie or raw_cookie, "x-xsrf-token": xsrf,
        "content-type": "application/grpc-web+proto", "x-grpc-web": "1"
    }
    url = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"
    tid = "Router-0100000000000000008B65AD"

    print(f"[*] Fetching WiFi Status for Router: {tid}")
    
    # Use WifiGetClientsRequest to see current clients and their basic event data
    req = Request(target_id=tid, wifi_get_clients=WifiGetClientsRequest())
    res = client.post(url, headers=headers, content=b'\x00' + len(req.SerializeToString()).to_bytes(4, 'big') + req.SerializeToString())
    if len(res.content) > 5:
        out = Response()
        out.ParseFromString(res.content[5:5+int.from_bytes(res.content[1:5], 'big')])
        if out.WhichOneof('response') == 'wifi_get_clients':
            d = MessageToDict(out.wifi_get_clients, preserving_proto_field_name=True)
            print("\n[ACTIVE WIFI CLIENTS]")
            clients = d.get('clients', [])
            for c in clients:
                name = c.get('name', 'Unknown')
                ip = c.get('ip_address', 'N/A')
                up = c.get('uptime_s', 0)
                print(f"  - Device: {name:20} | IP: {ip:15} | Uptime: {up}s")

if __name__ == "__main__": run()
