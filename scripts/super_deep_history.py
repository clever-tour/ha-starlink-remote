import httpx, re, json, sys, os, binascii
from pathlib import Path
from google.protobuf.json_format import MessageToDict

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "starlink_remote"))

from spacex.api.device.device_pb2 import Request, Response, GetHistoryRequest

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
    
    tid = "Router-0100000000000000008B65AD"
    print(f"[*] Deep History Probe for Router: {tid}")
    
    req = Request(target_id=tid, get_history=GetHistoryRequest())
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
            
            with open("super_history_dump.json", "w") as f: json.dump(d, f, indent=2)
            print(f"  [SUCCESS] Full history dumped to super_history_dump.json. Keys: {list(d.keys())}")
            
            # Search for ANY key that might contain a log or list
            for k in d.keys():
                if isinstance(d[k], list) and len(d[k]) > 0:
                    print(f"  Key '{k}' contains a list of {len(d[k])} items.")
                    if isinstance(d[k][0], dict):
                        print(f"    Sample item keys: {list(d[k][0].keys())}")
        else:
            print(f"  Failed. HTTP {res.status_code} | Len: {len(res.content)}")
    except Exception as e:
        print(f"  Error: {e}")

if __name__ == "__main__": run()
