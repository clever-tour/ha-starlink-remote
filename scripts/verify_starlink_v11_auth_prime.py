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
    
    # 1. PRIME ON API SUBDOMAIN
    print("[*] Priming on api.starlink.com...")
    headers = {"User-Agent": UA, "cookie": raw_cookie}
    try:
        r = client.get("https://api.starlink.com/auth-rp/auth/user", headers=headers)
        print(f"  [Prime] Status: {r.status_code}")
        # The key is to use the cookies from THIS response
        xsrf = client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')
        if not xsrf:
            m = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
            if m: xsrf = m.group(1)
        print(f"  [Prime] Live XSRF: {xsrf[:15]}...")
    except Exception as e:
        print(f"  [-] Prime Error: {e}")
        return

    auth_headers = {
        "User-Agent": UA, "cookie": raw_cookie, "x-xsrf-token": xsrf,
        "origin": "https://starlink.com", "referer": "https://starlink.com/account/home"
    }

    # 2. DISCOVERY
    print("\n[*] Discovering Hardware...")
    discovered = set()
    try:
        r = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=auth_headers)
        if r.status_code == 200:
            data = r.json()
            for res in data.get("content", {}).get("results", []):
                for ut in res.get("userTerminals", []):
                    uid = ut.get("userTerminalId")
                    if uid: discovered.add(f"ut{uid}")
                    for rtr in ut.get("routers", []):
                        rid = rtr.get("routerId")
                        if rid: discovered.add(f"Router-{rid}")
        print(f"  [Discovery] Status: {r.status_code} | Discovered: {discovered}")
    except: pass

    if not discovered:
        discovered = ["Router-0100000000000000008B65AD", "ut10588f9d-45017219-5815f472"]

    # 3. POLL
    url = "https://starlink.com/api/SpaceX.API.Device.Device/Handle"
    grpc_headers = auth_headers.copy()
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
                msg_len = int.from_bytes(res.content[1:5], 'big')
                out = Response()
                out.ParseFromString(res.content[5:5+msg_len])
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
