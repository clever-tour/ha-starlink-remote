import httpx, re, json, sys, os, binascii
from pathlib import Path
from google.protobuf.json_format import MessageToDict

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

    xsrf = ""
    xsrf_match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if xsrf_match:
        xsrf = xsrf_match.group(1)
        print(f"[+] Found XSRF Token: {xsrf[:15]}...")

    client = httpx.Client(http2=True, follow_redirects=True)
    
    headers = {
        "User-Agent": UA,
        "cookie": raw_cookie,
        "origin": "https://www.starlink.com",
        "referer": "https://www.starlink.com/account/home",
        "x-xsrf-token": xsrf,
        "accept": "*/*",
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1"
    }

    # Known Hardware IDs
    targets = ["ut10588f9d-45017219-5815f472", "Router-0100000000000000008B65AD"]
    url = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"

    for tid in targets:
        print(f"\n>>> TARGET: {tid}")
        req = Request(target_id=tid, get_status=GetStatusRequest())
        ser = req.SerializeToString()
        frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
        
        try:
            res = client.post(url, headers=headers, content=frame)
            print(f"  [HTTP] {res.status_code} | Length: {len(res.content)}")
            
            if len(res.content) > 5:
                msg_len = int.from_bytes(res.content[1:5], 'big')
                out = Response()
                out.ParseFromString(res.content[5:5+msg_len])
                rt = out.WhichOneof('response')
                if rt:
                    print(f"  [SUCCESS] Received: {rt}")
                    rd = MessageToDict(getattr(out, rt), preserving_proto_field_name=True)
                    if 'downlink_throughput_bps' in rd:
                        print(f"    - Downlink: {round(float(rd['downlink_throughput_bps'])/1e6, 2)} Mbps")
                    if 'clients' in rd:
                        print(f"    - WiFi Clients: {len(rd['clients'])}")
                else:
                    print("  [-] Empty Response object.")
            else:
                print(f"  [-] Body too short: {binascii.hexlify(res.content)}")
        except Exception as e:
            print(f"  [-] Poll Error: {e}")

if __name__ == "__main__":
    run_test()
