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
    
    # 1. Establish Session on API subdomain
    headers = {
        "User-Agent": UA,
        "cookie": raw_cookie,
        "origin": "https://starlink.com",
        "referer": "https://starlink.com/account/home"
    }
    
    print("[*] Verifying API Auth...")
    try:
        r = client.get("https://api.starlink.com/auth-rp/auth/user", headers=headers)
        print(f"  [Auth] Status: {r.status_code}")
        # Capture XSRF from this specific response if provided
        xsrf = client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')
        if not xsrf:
            # Fallback to cookie string search
            m = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
            if m: xsrf = m.group(1)
        print(f"  [Auth] Using XSRF: {xsrf[:15]}...")
    except Exception as e:
        print(f"  [-] Auth Error: {e}")
        return

    # 2. Discovery
    print("\n[*] Step 1: Hardware Discovery...")
    discovered = set()
    headers['x-xsrf-token'] = xsrf
    try:
        r = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=headers)
        print(f"  [Discovery] Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            for res in data.get("content", {}).get("results", []):
                for ut in res.get("userTerminals", []):
                    uid = ut.get("userTerminalId")
                    if uid: discovered.add(f"ut{uid}")
                    for rtr in ut.get("routers", []):
                        rid = rtr.get("routerId")
                        if rid: discovered.add(f"Router-{rid}")
        print(f"  [+] Discovered: {discovered}")
    except Exception as e:
        print(f"  [-] Discovery Error: {e}")

    if not discovered:
        discovered = {"Router-0100000000000000008B65AD", "ut10588f9d-45017219-5815f472"}

    # 3. Polling via WWW subdomain (verified tunnel)
    print("\n[*] Step 2: Telemetry Polling...")
    url = "https://starlink.com/api/SpaceX.API.Device.Device/Handle"
    grpc_headers = headers.copy()
    grpc_headers.update({"content-type": "application/grpc-web+proto", "x-grpc-web": "1"})
    
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
