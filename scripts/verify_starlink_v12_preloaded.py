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

    client = httpx.Client(http2=True, follow_redirects=True)
    
    # 1. Discover via window.__PRELOADED_STATE__
    print("[*] Discovering via Account Home HTML...")
    headers = {"User-Agent": UA, "cookie": raw_cookie}
    discovered = set()
    try:
        r = client.get("https://www.starlink.com/account/home", headers=headers)
        if r.status_code == 200:
            # Look for IDs in the preloaded state
            routers = re.findall(r"Router-[A-Fa-f0-9]{24}", r.text)
            uts = re.findall(r"ut[a-f0-9-]{36}", r.text)
            discovered.update(routers)
            discovered.update(uts)
        print(f"  [Discovery] Status: {r.status_code} | Found: {discovered}")
    except Exception as e:
        print(f"  [-] Discovery Error: {e}")

    if not discovered:
        discovered = ["Router-0100000000000000008B65AD", "ut10588f9d-45017219-5815f472"]

    # 2. Extract XSRF from the PRE-COOKIE
    xsrf = ""
    xsrf_match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if xsrf_match: xsrf = xsrf_match.group(1)

    # 3. POLL
    url = "https://starlink.com/api/SpaceX.API.Device.Device/Handle"
    grpc_headers = {
        "User-Agent": UA, "cookie": raw_cookie, "x-xsrf-token": xsrf,
        "origin": "https://starlink.com", "referer": "https://starlink.com/account/home",
        "content-type": "application/grpc-web+proto", "x-grpc-web": "1"
    }
    
    for tid in discovered:
        print(f"\n>>> TARGET: {tid}")
        req = Request(target_id=tid, get_status=GetStatusRequest())
        ser = req.SerializeToString()
        frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
        
        try:
            res = client.post(url, headers=grpc_headers, content=frame)
            print(f"  [HTTP] {res.status_code} | Bytes: {len(res.content)}")
            if len(res.content) > 5:
                out = Response()
                out.ParseFromString(res.content[5:5+int.from_bytes(res.content[1:5], 'big')])
                rt = out.WhichOneof('response')
                if rt:
                    print(f"  [SUCCESS] Received: {rt}")
                    rd = MessageToDict(getattr(out, rt), preserving_proto_field_name=True)
                    if 'downlink_throughput_bps' in rd:
                        print(f"    - Downlink: {round(float(rd['downlink_throughput_bps'])/1e6, 2)} Mbps")
        except Exception as e:
            print(f"  [-] Poll Error: {e}")

if __name__ == "__main__":
    run_test()
