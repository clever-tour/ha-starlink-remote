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
    if not os.path.exists("cookie.txt"):
        print("[-] cookie.txt not found.")
        return

    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    # 1. Extract XSRF and Session Info
    xsrf = ""
    xsrf_match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if xsrf_match:
        xsrf = xsrf_match.group(1)
        print(f"[+] Found XSRF Token: {xsrf[:15]}...")

    # 2. Setup Client (Matches browser TLS/HTTP2 behavior)
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

    # 3. Discovery via Service Lines API
    print("[*] Discovery Step...")
    discovered = set()
    try:
        r = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=headers)
        if r.status_code == 200:
            data = r.json()
            for res in data.get("content", {}).get("results", []):
                for ut in res.get("userTerminals", []):
                    uid = ut.get("userTerminalId")
                    if uid: discovered.add(f"ut{uid}")
                    for rtr in ut.get("routers", []):
                        rid = rtr.get("routerId")
                        if rid: discovered.add(f"Router-{rid}")
        print(f"  [+] Discovered Hardware: {discovered}")
    except Exception as e:
        print(f"  [-] Discovery Error: {e}")

    # Fallback to known IDs if API discovery was empty
    if not discovered:
        discovered = {"Router-0100000000000000008B65AD", "ut10588f9d-45017219-5815f472"}

    # 4. Polling Step
    url = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"
    for tid in discovered:
        print(f"\n>>> TARGET: {tid}")
        req = Request(target_id=tid, get_status=GetStatusRequest())
        ser = req.SerializeToString()
        # gRPC-Web Frame: 0 (Data) + 4-byte length + payload
        frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
        
        print(f"  [OUT] Hex: {binascii.hexlify(frame[:20]).decode()}... (Total {len(frame)} bytes)")
        
        try:
            res = client.post(url, headers=headers, content=frame)
            print(f"  [IN ] HTTP {res.status_code} | Length: {len(res.content)}")
            
            if len(res.content) > 5:
                # Check for gRPC trailers or compressed bit
                first_byte = res.content[0]
                msg_len = int.from_bytes(res.content[1:5], 'big')
                print(f"  [IN ] Frame Type: {first_byte} | Msg Length: {msg_len}")
                
                if first_byte == 0 and len(res.content) >= 5 + msg_len:
                    out = Response()
                    out.ParseFromString(res.content[5:5+msg_len])
                    rt = out.WhichOneof('response')
                    if rt:
                        print(f"  [IN ] SUCCESS: Received {rt}")
                        data = MessageToDict(getattr(out, rt), preserving_proto_field_name=True)
                        if 'clients' in data:
                            print(f"    - WiFi Clients: {len(data['clients'])}")
                        if 'downlink_throughput_bps' in data:
                            print(f"    - Downlink: {round(float(data['downlink_throughput_bps'])/1e6, 2)} Mbps")
                    else:
                        print("  [!] No sub-message in response.")
                else:
                    print(f"  [!] Invalid frame or mismatch. Body Hex: {binascii.hexlify(res.content[:20]).decode()}")
            else:
                print("  [-] Response too short to be valid gRPC.")
        except Exception as e:
            print(f"  [-] Connection Error: {e}")

if __name__ == "__main__":
    run_test()
