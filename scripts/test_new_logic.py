import sys
import httpx, re, json, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    if not os.path.exists("cookie.txt"):
        print("[-] cookie.txt not found")
        return

    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    
    # Extract XSRF from cookie string for headers
    xsrf = ""
    match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if match:
        xsrf = match.group(1)

    headers = {
        "User-Agent": UA,
        "cookie": raw_cookie,
        "x-xsrf-token": xsrf,
        "origin": "https://www.starlink.com",
        "referer": "https://www.starlink.com/account/home"
    }

    # 1. DISCOVERY
    print("[*] Accessing subscription page for discovery...")
    try:
        r = client.get("https://www.starlink.com/account/service-line", headers=headers)
        print(f"  [HTTP] Status: {r.status_code}")
        
        # Look for selectedDevice= in the HTML
        ids = set(re.findall(r'selectedDevice=([A-Fa-f0-9-]+)', r.text))
        # Standard patterns
        uts = set(re.findall(r"ut[a-f0-9-]{36}", r.text))
        routers = set(re.findall(r"Router-[A-Fa-f0-9]{24}", r.text))
        
        discovered = ids | uts | routers
        print(f"  [+] Discovered IDs: {discovered}")

        if not discovered:
            print("  [!] No IDs found. Trying preloaded state...")
            state_match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*({.*?});', r.text)
            if state_match:
                print("    [+] Found preloaded state, searching for IDs...")
                found_in_state = set(re.findall(r'"(ut[a-f0-9-]{36})"', state_match.group(1)))
                found_in_state.update(re.findall(r'"(Router-[A-Fa-f0-9]{24})"', state_match.group(1)))
                discovered.update(found_in_state)
                print(f"    [+] Discovered in state: {found_in_state}")

        # 2. TELEMETRY API
        if discovered:
            print("\n[*] Testing Telemetry API (Query)...")
            url = "https://www.starlink.com/api/public/v2/telemetry/query"
            
            # Based on docs, it might return all associated devices if we provide the right schema
            body = {
                "columnNamesByDeviceType": {
                    "u": ["DeviceType", "UtcTimestampNs", "DeviceId", "PingLatencyMsAvg", "PingDropRateAvg"],
                    "r": ["DeviceType", "UtcTimestampNs", "DeviceId", "Uptime", "PingLatencyMs"]
                }
            }
            
            r_api = client.post(url, headers=headers, json=body)
            print(f"  [API Query] Status: {r_api.status_code}")
            if r_api.status_code == 200:
                print("  [SUCCESS] Received Telemetry Data:")
                print(json.dumps(r_api.json(), indent=2))
            else:
                print(f"  [-] Error: {r_api.text}")
                
                # Try hitting the gRPC endpoint as fallback if REST fails
                print("\n[*] Fallback: Testing gRPC-Web endpoint with discovered IDs...")
                from spacex.api.device.device_pb2 import Request, GetStatusRequest, Response
                grpc_url = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"
                headers.update({"content-type": "application/grpc-web+proto", "x-grpc-web": "1"})
                
                for tid in discovered:
                    print(f"    >>> Polling {tid}...")
                    req = Request(target_id=tid, get_status=GetStatusRequest())
                    ser = req.SerializeToString()
                    frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
                    res = client.post(grpc_url, headers=headers, content=frame)
                    print(f"      [HTTP] {res.status_code} | Bytes: {len(res.content)}")
                    if res.status_code == 200 and len(res.content) > 5:
                        print("      [SUCCESS] gRPC-Web working for this ID.")

    except Exception as e:
        print(f"  [-] Error: {e}")

if __name__ == "__main__":
    # Ensure spacex imports work
    sys.path.insert(0, os.path.join(os.getcwd(), "custom_components/starlink_remote"))
    run_test()
