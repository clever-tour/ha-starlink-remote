import httpx, re, json, sys, os
from pathlib import Path
from google.protobuf.json_format import MessageToDict

# Setup paths for spacex imports
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "starlink_remote"))

try:
    from spacex.api.device.device_pb2 import Request, GetStatusRequest, GetHistoryRequest, Response
except ImportError:
    print("[-] Error: Could not import protobuf definitions.")
    sys.exit(1)

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    if not os.path.exists("cookie.txt"):
        print("[-] cookie.txt not found.")
        return

    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    
    # Extract XSRF
    xsrf = ""
    xsrf_match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if xsrf_match:
        xsrf = xsrf_match.group(1)
        print(f"[+] Found XSRF Token: {xsrf[:10]}...")

    headers = {
        "User-Agent": UA,
        "cookie": raw_cookie,
        "origin": "https://starlink.com",
        "referer": "https://starlink.com/account/home"
    }
    if xsrf:
        headers["x-xsrf-token"] = xsrf

    # 1. Hardware Discovery
    print("[*] Discovering Hardware...")
    discovered_ids = set()
    try:
        r = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=headers)
        if r.status_code == 200:
            data = r.json()
            for res in data.get("content", {}).get("results", []):
                for ut in res.get("userTerminals", []):
                    uid = ut.get("userTerminalId")
                    if uid: discovered_ids.add(f"ut{uid}")
                    for rtr in ut.get("routers", []):
                        rid = rtr.get("routerId")
                        if rid: discovered_ids.add(f"Router-{rid}")
        print(f"  [+] Discovered: {discovered_ids}")
    except Exception as e:
        print(f"  [-] Discovery failed: {e}")

    if not discovered_ids:
        discovered_ids = {"Router-0100000000000000008B65AD", "ut10588f9d-45017219-5815f472"}
        print(f"  [!] Using hardcoded fallbacks: {discovered_ids}")

    # 2. Polling Logic
    url = "https://starlink.com/api/SpaceX.API.Device.Device/Handle"
    for tid in discovered_ids:
        print(f"\n>>> Polling: {tid}")
        
        # Test Status
        req = Request(target_id=tid, get_status=GetStatusRequest())
        ser = req.SerializeToString()
        frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
        
        grpc_headers = headers.copy()
        grpc_headers.update({
            "content-type": "application/grpc-web+proto",
            "x-grpc-web": "1"
        })

        try:
            res = client.post(url, headers=grpc_headers, content=frame)
            print(f"  [Status] HTTP {res.status_code} | Bytes: {len(res.content)}")
            if len(res.content) > 5:
                msg_len = int.from_bytes(res.content[1:5], 'big')
                out = Response()
                out.ParseFromString(res.content[5:5+msg_len])
                rt = out.WhichOneof('response')
                if rt:
                    rd = MessageToDict(getattr(out, rt), preserving_proto_field_name=True)
                    print(f"  [SUCCESS] {rt}")
                    if 'downlink_throughput_bps' in rd:
                        print(f"    - Downlink: {round(float(rd['downlink_throughput_bps'])/1e6, 2)} Mbps")
                    if 'clients' in rd:
                        print(f"    - WiFi Clients: {len(rd['clients'])}")
                else:
                    print("  [-] No response sub-message found.")
            else:
                print("  [-] Empty payload.")
        except Exception as e:
            print(f"  [-] Poll failed: {e}")

if __name__ == "__main__":
    run_test()
