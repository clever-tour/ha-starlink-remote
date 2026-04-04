import httpx, re, json, sys, os, binascii
from pathlib import Path
from google.protobuf.json_format import MessageToDict

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "starlink_remote"))

from spacex.api.device.device_pb2 import Request, Response, GetStatusRequest

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run():
    with open("cookie.txt", "r") as f: raw_cookie = f.read().strip()
    client = httpx.Client(http2=True, follow_redirects=True)
    
    print("[*] Priming Session...")
    client.get("https://www.starlink.com/account/home", headers={"User-Agent": UA, "cookie": raw_cookie})
    xsrf = client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')

    headers = {
        "User-Agent": UA, "cookie": raw_cookie, "x-xsrf-token": xsrf,
        "content-type": "application/grpc-web+proto", "x-grpc-web": "1"
    }
    url = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"
    
    ids = ["ut10588f9d-45017219-5815f472", "Router-0100000000000000008B65AD"]

    for tid in ids:
        print(f"\n[*] Fetching Status/Alerts for: {tid}")
        req = Request(target_id=tid, get_status=GetStatusRequest())
        ser = req.SerializeToString()
        frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
        
        try:
            res = client.post(url, headers=headers, content=frame)
            if res.status_code == 200 and len(res.content) > 5:
                msg_len = int.from_bytes(res.content[1:5], 'big')
                out = Response()
                out.ParseFromString(res.content[5:5+msg_len])
                rt = out.WhichOneof('response')
                d = MessageToDict(getattr(out, rt), preserving_proto_field_name=True)
                
                print(f"  [SUCCESS] Received {rt}. Checking for alerts...")
                
                # Check for common alert keys
                if rt == 'dish_get_status':
                    alerts = d.get('alerts', {})
                    print(f"  Dish Alerts: {json.dumps(alerts, indent=2)}")
                elif rt == 'wifi_get_status':
                    # Router alerts are often in a different structure
                    print(f"  Router Status Keys: {list(d.keys())}")
                    # Look for anything named alert or issue
                    for k in d.keys():
                        if 'alert' in k.lower() or 'issue' in k.lower() or 'event' in k.lower():
                            print(f"  Found potential alert key: {k}")
                            print(f"  {k}: {json.dumps(d[k], indent=2)}")
            else:
                print(f"  Failed. HTTP {res.status_code} | Len: {len(res.content)}")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__": run()
