import httpx, re, json, sys, os, binascii
from pathlib import Path
from google.protobuf.json_format import MessageToDict

# Setup paths for spacex imports
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "starlink_remote"))

try:
    from spacex.api.device.device_pb2 import Request, GetStatusRequest, Response
except ImportError:
    print("[-] Error: Could not import protobuf definitions.")
    sys.exit(1)

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    for part in raw_cookie.split(';'):
        if '=' in part:
            k, v = part.strip().split('=', 1)
            client.cookies.set(k, v, domain='.starlink.com')

    # Prime XSRF
    client.get("https://www.starlink.com/account/home", headers={"User-Agent": UA})
    xsrf = client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')

    url = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"
    
    # Try different ID formats for the same hardware
    variants = [
        "ut10588f9d-45017219-5815f472",  # With prefix
        "10588f9d-45017219-5815f472",    # Without prefix
        "Router-0100000000000000008B65AD", # Router with prefix
        "0100000000000000008B65AD"         # Router without prefix
    ]

    for tid in variants:
        print(f"\n>>> TESTING ID: {tid}")
        req = Request(target_id=tid, get_status=GetStatusRequest())
        ser = req.SerializeToString()
        frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
        
        headers = {
            "User-Agent": UA,
            "origin": "https://www.starlink.com",
            "referer": "https://www.starlink.com/account/home",
            "x-xsrf-token": xsrf,
            "content-type": "application/grpc-web+proto",
            "x-grpc-web": "1",
            "grpc-timeout": "10S"
        }
        
        try:
            res = client.post(url, headers=headers, content=frame)
            print(f"  [HTTP] {res.status_code} | Bytes: {len(res.content)}")
            if len(res.content) > 5:
                out = Response()
                out.ParseFromString(res.content[5:5+int.from_bytes(res.content[1:5], 'big')])
                rt = out.WhichOneof('response')
                if rt:
                    print(f"  [SUCCESS] Received {rt}")
                    return # Exit on first success
        except: pass

if __name__ == "__main__":
    run_test()
