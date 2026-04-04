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

    # Extract XSRF for the header
    xsrf = ""
    xsrf_match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if xsrf_match:
        xsrf = xsrf_match.group(1)
        print(f"[+] Found XSRF Token: {xsrf[:15]}...")

    client = httpx.Client(http2=True, follow_redirects=True)
    
    # Headers must match exactly what works in the browser
    common_headers = {
        "User-Agent": UA,
        "cookie": raw_cookie,
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

    # 2. Polling Logic - The Primary Tunnel
    # Verified: starlink.com/api/... is the most stable tunnel for gRPC-Web
    url = "https://starlink.com/api/SpaceX.API.Device.Device/Handle"
    
    discovered_ids = ["Router-0100000000000000008B65AD", "ut10588f9d-45017219-5815f472"]
    
    grpc_headers = common_headers.copy()
    grpc_headers.update({
        "accept": "*/*",
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1"
    })

    for tid in discovered_ids:
        print(f"\n>>> Polling Target: {tid}")
        req = Request(target_id=tid, get_status=GetStatusRequest())
        ser = req.SerializeToString()
        # Binary frame: 0x00 + 4-byte len + payload
        frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
        
        try:
            res = client.post(url, headers=grpc_headers, content=frame)
            print(f"  [HTTP] Status: {res.status_code} | Body Length: {len(res.content)}")
            
            if len(res.content) > 5:
                # Binary gRPC-Web framing check
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
                    print("  [-] Response sub-message was empty.")
            else:
                print(f"  [-] Empty/Short payload received.")
        except Exception as e:
            print(f"  [-] Poll Error: {e}")

if __name__ == "__main__":
    run_test()
