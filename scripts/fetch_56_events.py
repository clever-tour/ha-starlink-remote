import httpx, re, json, sys, os, binascii
from pathlib import Path
from google.protobuf.json_format import MessageToDict

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "starlink_remote"))

from spacex.api.device.device_pb2 import Request, Response, GetStatusRequest

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run():
    # Use root cookie.txt for scripts
    with open("cookie.txt", "r") as f: raw_cookie = f.read().strip()
    client = httpx.Client(http2=True, follow_redirects=True)
    
    print("[*] Priming Session...")
    client.get("https://www.starlink.com/account/home", headers={"User-Agent": UA, "cookie": raw_cookie})
    xsrf = client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')
    client.get("https://api.starlink.com/auth-rp/auth/user", headers={"User-Agent": UA, "cookie": raw_cookie, "x-xsrf-token": xsrf})

    fresh_cookie = "; ".join([f"{c.name}={c.value}" for c in client.cookies.jar])
    headers = {"User-Agent": UA, "cookie": fresh_cookie or raw_cookie, "x-xsrf-token": xsrf}

    # Discovery
    r_sl = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=headers)
    sl_num = r_sl.json()['content']['results'][0]['serviceLineNumber']
    
    # We found that gRPC-Web status contains 'alerts'
    ids = ["ut10588f9d-45017219-5815f472", "Router-0100000000000000008B65AD"]
    
    url = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"
    
    print(f"\n[*] Fetching 56 Events via gRPC Status/Alerts...")
    
    event_list = []

    for tid in ids:
        req = Request(target_id=tid, get_status=GetStatusRequest())
        ser = req.SerializeToString()
        frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
        res = client.post(url, headers=headers, content=frame)
        
        if res.status_code == 200 and len(res.content) > 5:
            msg_len = int.from_bytes(res.content[1:5], 'big')
            out = Response()
            out.ParseFromString(res.content[5:5+msg_len])
            rt = out.WhichOneof('response')
            d = MessageToDict(getattr(out, rt), preserving_proto_field_name=True)
            
            alerts = d.get('alerts', {})
            for a_name, active in alerts.items():
                if active:
                    event_list.append({
                        "device": tid,
                        "event": a_name.replace("_", " ").title(),
                        "type": "ACTIVE_ALERT"
                    })
            
            # Map specific hardware info to "Events"
            if rt == 'dish_get_status':
                if d.get('is_snr_above_noise_floor') == False:
                    event_list.append({"device": tid, "event": "Low SNR", "type": "STATE"})
                if d.get('obstruction_stats', {}).get('currently_obstructed'):
                    event_list.append({"device": tid, "event": "Obstructed", "type": "STATE"})
            
            if rt == 'wifi_get_status':
                # Check for software update event
                upd = d.get('software_update_stats', {})
                if upd.get('state') != 'NO_UPDATE_REQUIRED':
                    event_list.append({"device": tid, "event": f"Software Update: {upd.get('state')}", "type": "UPDATE"})

    print(f"\n[SUMMARY: {len(event_list)} Events Found]")
    for e in event_list:
        print(f"  - [{e['type']}] {e['event']} ({e['device'][:10]}...)")

if __name__ == "__main__": run()
