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
    
    # 1. Establish Session and Refresh Cookie
    print("[*] Priming Session & Fetching Fresh Cookie...")
    headers = {"User-Agent": UA, "cookie": raw_cookie}
    try:
        # Hit home page to ensure we have a fresh session token/XSRF
        r = client.get("https://www.starlink.com/account/home", headers=headers)
        print(f"  [HTTP] Status: {r.status_code}")
        
        # Capture fresh cookie string from client jar
        fresh_cookie = "; ".join([f"{c.name}={c.value}" for c in client.cookies.jar])
        # Merge with initial cookies to ensure we keep the SSO tokens
        # (This mimics the browser's persistent state)
        
        # 2. Discover Hardware IDs
        print("\n[*] Discovering Hardware IDs from Account Dashboard...")
        # Method A: window.__PRELOADED_STATE__
        discovered_ids = set()
        state_match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*({.*?});', r.text)
        if state_match:
            print("  [+] Found Preloaded State")
            # Look for serial numbers or target IDs
            ids = re.findall(r'"([A-Fa-f0-9]{24})"', state_match.group(1))
            uts = re.findall(r'"(ut[a-f0-9-]{36})"', state_match.group(1))
            discovered_ids.update(ids)
            discovered_ids.update(uts)
        
        # Method B: selectedDevice in URLs
        dev_urls = re.findall(r'selectedDevice=([A-Fa-f0-9-]+)', r.text)
        discovered_ids.update(dev_urls)
        
        # Method C: service-lines API
        xsrf = client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')
        api_headers = {
            "User-Agent": UA, "cookie": fresh_cookie or raw_cookie, "x-xsrf-token": xsrf,
            "origin": "https://www.starlink.com", "referer": "https://www.starlink.com/account/home"
        }
        r_lines = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=api_headers)
        if r_lines.status_code == 200:
            data = r_lines.json()
            for res in data.get("content", {}).get("results", []):
                for ut in res.get("userTerminals", []):
                    uid = ut.get("userTerminalId")
                    if uid: discovered_ids.add(f"ut{uid}")
                    for rtr in ut.get("routers", []):
                        rid = rtr.get("routerId")
                        if rid: discovered_ids.add(f"Router-{rid}")

        print(f"  [+] FINAL DISCOVERED IDS: {discovered_ids}")

        if not discovered_ids:
            print("  [!] No IDs discovered. Polling will fail.")
            return

        # 3. Telemetry Polling
        print("\n[*] Step 3: Telemetry Polling (gRPC-Web)...")
        url = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"
        
        for tid in discovered_ids:
            print(f"\n>>> TARGET: {tid}")
            req = Request(target_id=tid, get_status=GetStatusRequest())
            ser = req.SerializeToString()
            frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
            
            poll_headers = api_headers.copy()
            poll_headers.update({"content-type": "application/grpc-web+proto", "x-grpc-web": "1"})
            
            try:
                res = client.post(url, headers=poll_headers, content=frame)
                print(f"  [HTTP] Status: {res.status_code} | Length: {len(res.content)}")
                if len(res.content) > 5:
                    msg_len = int.from_bytes(res.content[1:5], 'big')
                    out = Response()
                    out.ParseFromString(res.content[5:5+msg_len])
                    rt = out.WhichOneof('response')
                    if rt:
                        print(f"  [SUCCESS] Received: {rt}")
                        data = MessageToDict(getattr(out, rt), preserving_proto_field_name=True)
                        if 'clients' in data:
                            print(f"    - WiFi Clients: {len(data['clients'])}")
                        if 'downlink_throughput_bps' in data:
                            print(f"    - Downlink: {round(float(data['downlink_throughput_bps'])/1e6, 2)} Mbps")
            except Exception as e:
                print(f"  [-] Poll Error: {e}")

    except Exception as e:
        print(f"  [-] Diagnostic Error: {e}")

if __name__ == "__main__":
    run_test()
