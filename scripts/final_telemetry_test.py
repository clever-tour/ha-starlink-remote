import os, httpx, re, json, sys, struct
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
        cookie_str = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    
    # Extract XSRF
    xsrf = ""
    xsrf_match = re.search(r'XSRF-TOKEN=([^;]+)', cookie_str)
    if xsrf_match:
        xsrf = xsrf_match.group(1)
        print(f"[+] Found XSRF Token: {xsrf[:10]}...")

    common_headers = {
        "User-Agent": UA,
        "cookie": cookie_str,
        "origin": "https://starlink.com",
        "referer": "https://starlink.com/account/home"
    }
    if xsrf:
        common_headers["x-xsrf-token"] = xsrf

    # 1. Verify Auth
    print("[*] Verifying Account Access...")
    try:
        r = client.get("https://api.starlink.com/auth-rp/auth/user", headers=common_headers)
        print(f"  [HTTP] Status: {r.status_code}")
        if r.status_code != 200:
            print("  [-] Auth Failed. Check your cookie.")
            return
    except Exception as e:
        print(f"  [-] Connection Error: {e}")
        return

    # 2. Discover Hardware
    print("\n[*] Discovering Hardware IDs...")
    discovered_ids = set()
    # User's confirmed IDs
    discovered_ids.add("Router-0100000000000000008B65AD")
    discovered_ids.add("ut10588f9d-45017219-5815f472")

    # Try to find others via API
    try:
        r = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=common_headers)
        if r.status_code == 200:
            data = r.json()
            for res in data.get("content", {}).get("results", []):
                for ut in res.get("userTerminals", []):
                    uid = ut.get("userTerminalId")
                    if uid: discovered_ids.add(f"ut{uid}")
                    for rtr in ut.get("routers", []):
                        rid = rtr.get("routerId")
                        if rid: discovered_ids.add(f"Router-{rid}")
    except: pass
    
    print(f"  [+] Working with IDs: {discovered_ids}")

    # 3. Poll Telemetry
    print("\n[*] Polling Telemetry...")
    url = "https://starlink.com/api/SpaceX.API.Device.Device/Handle"
    
    for tid in discovered_ids:
        print(f"\n>>> Polling: {tid}")
        req = Request(target_id=tid, get_status=GetStatusRequest())
        ser = req.SerializeToString()
        frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
        
        headers = common_headers.copy()
        headers["content-type"] = "application/grpc-web+proto"
        headers["x-grpc-web"] = "1"
        headers["accept"] = "*/*"

        try:
            res = client.post(url, headers=headers, content=frame)
            print(f"  [HTTP] Status: {res.status_code}")
            print(f"  [gRPC] Status Header: {res.headers.get('grpc-status')}")
            print(f"  [DATA] Bytes Received: {len(res.content)}")
            
            if len(res.content) > 5:
                msg_len = int.from_bytes(res.content[1:5], 'big')
                out = Response()
                out.ParseFromString(res.content[5:5+msg_len])
                rt = out.WhichOneof('response')
                if rt:
                    rd = MessageToDict(getattr(out, rt), preserving_proto_field_name=True)
                    print(f"  [SUCCESS] Received {rt}")
                    # Dump a few key values to prove it's live
                    if rt == 'dish_get_status':
                        print(f"    - Downlink: {rd.get('downlink_throughput_bps', 0)} bps")
                        print(f"    - Azimuth: {rd.get('boresight_azimuth_deg', 'N/A')}")
                    elif rt == 'wifi_get_status':
                        print(f"    - Clients: {len(rd.get('clients', []))}")
                else:
                    print("  [-] Empty gRPC response object.")
            else:
                print("  [-] No payload in response.")
        except Exception as e:
            print(f"  [-] Poll Error: {e}")

if __name__ == "__main__":
    run_test()
