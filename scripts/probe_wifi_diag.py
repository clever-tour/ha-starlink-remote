import httpx, re, json, sys, os, binascii
from pathlib import Path
from google.protobuf.json_format import MessageToDict

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "starlink_remote"))

from spacex.api.device.device_pb2 import Request, GetDiagnosticsRequest, Response

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

    print(f"[*] Fetching WiFi Diag for Router: {tid}")
    
    req = Request(target_id=tid, get_diagnostics=GetDiagnosticsRequest())
    res = client.post(url, headers=headers, content=b'\x00' + len(req.SerializeToString()).to_bytes(4, 'big') + req.SerializeToString())
    if len(res.content) > 5:
        out = Response()
        out.ParseFromString(res.content[5:5+int.from_bytes(res.content[1:5], 'big')])
        rt = out.WhichOneof('response')
        print(f"  Received Response Type: {rt}")
        if rt == 'wifi_get_diagnostics':
            d = MessageToDict(out.wifi_get_diagnostics, preserving_proto_field_name=True)
            print(json.dumps(d, indent=2))

if __name__ == "__main__": run()
