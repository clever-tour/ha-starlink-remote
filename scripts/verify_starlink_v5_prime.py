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

    # 1. Setup Persistent Client with Initial Cookie
    client = httpx.Client(http2=True, follow_redirects=True)
    # Load initial cookies into jar
    for part in raw_cookie.split(';'):
        if '=' in part:
            k, v = part.strip().split('=', 1)
            client.cookies.set(k, v, domain='.starlink.com')

    def get_live_headers():
        xsrf = client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')
        return {
            "User-Agent": UA,
            "origin": "https://www.starlink.com",
            "referer": "https://www.starlink.com/account/home",
            "x-xsrf-token": xsrf,
            "accept": "*/*"
        }

    # 2. Prime the Session (Capture fresh XSRF)
    print("[*] Priming Session...")
    try:
        r = client.get("https://www.starlink.com/account/home", headers={"User-Agent": UA})
        print(f"  [Prime] Status: {r.status_code}")
        print(f"  [Prime] Live XSRF: {client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')[:15]}...")
    except Exception as e:
        print(f"  [-] Prime Error: {e}")

    # 3. Discovery
    print("\n[*] Step 1: Hardware Discovery...")
    discovered = set()
    try:
        r = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=get_live_headers())
        print(f"  [HTTP] Status: {r.status_code}")
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
        print(f"  [!] Using fallbacks: {discovered}")

    # 4. Telemetry Polling
    print("\n[*] Step 2: Telemetry Polling...")
    url = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"
    
    for tid in discovered:
        print(f"\n>>> Polling Target: {tid}")
        req = Request(target_id=tid, get_status=GetStatusRequest())
        ser = req.SerializeToString()
        frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
        
        headers = get_live_headers()
        headers.update({"content-type": "application/grpc-web+proto", "x-grpc-web": "1"})
        
        try:
            res = client.post(url, headers=headers, content=frame)
            print(f"  [HTTP] Status: {res.status_code} | Length: {len(res.content)}")
            
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
