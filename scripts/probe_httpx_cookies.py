import httpx, re, json, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    # Use a persistent client to manage cookies
    with httpx.Client(http2=True, follow_redirects=True) as client:
        # Load initial cookies into jar
        for part in raw_cookie.split(';'):
            if '=' in part:
                k, v = part.strip().split('=', 1)
                client.cookies.set(k, v, domain='.starlink.com')

        xsrf = client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')
        
        common_headers = {
            "User-Agent": UA, "x-xsrf-token": xsrf,
            "origin": "https://www.starlink.com", "referer": "https://www.starlink.com/account/home"
        }

        # 1. PRIME
        print("[*] Priming via www.starlink.com...")
        r1 = client.get("https://www.starlink.com/account/home", headers=common_headers)
        print(f"  [Prime 1] Status: {r1.status_code}")

        # 2. PRIME API SUBDOMAIN
        print("[*] Priming via api.starlink.com...")
        r2 = client.get("https://api.starlink.com/auth-rp/auth/user", headers=common_headers)
        print(f"  [Prime 2] Status: {r2.status_code}")

        # 3. DISCOVERY
        print("[*] Fetching service-lines...")
        r_ids = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=common_headers)
        print(f"  [Discovery] Status: {r_ids.status_code}")
        if r_ids.status_code == 200:
            print("  [SUCCESS] Found IDs.")
        else:
            print(f"  [-] Failed: {r_ids.text}")

        # 4. TELEMETRY
        print("[*] Fetching Telemetry...")
        body = {
            "columnNamesByDeviceType": {
                "u": ["DeviceType", "UtcTimestampNs", "DeviceId", "PingLatencyMsAvg", "PingDropRateAvg"],
                "r": ["DeviceType", "UtcTimestampNs", "DeviceId", "Uptime", "PingLatencyMs"]
            }
        }
        r_api = client.post("https://api.starlink.com/public/v2/telemetry/query", headers=common_headers, json=body)
        print(f"  [Telemetry] Status: {r_api.status_code}")
        if r_api.status_code == 200:
            print(json.dumps(r_api.json(), indent=2))
        else:
            print(f"  [-] Failed: {r_api.text}")

if __name__ == "__main__":
    run_test()
