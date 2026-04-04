import httpx, re, json, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    headers = {"User-Agent": UA, "cookie": raw_cookie}
    
    # 1. PRIME (Get fresh Access token)
    print("[*] Priming session from www.starlink.com...")
    try:
        r_prime = client.get("https://www.starlink.com/account/home", headers=headers)
        print(f"  [Prime] Status: {r_prime.status_code}")
        
        # Update session cookies from response
        fresh_cookies = "; ".join([f"{c.name}={c.value}" for c in client.cookies.jar])
        # We must ALSO keep the original SSO cookies if they weren't in the jar
        
        xsrf = client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')
        if not xsrf:
            m = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
            if m: xsrf = m.group(1)

        api_headers = {
            "User-Agent": UA, "cookie": fresh_cookies or raw_cookie, "x-xsrf-token": xsrf,
            "Content-Type": "application/json",
            "origin": "https://www.starlink.com", "referer": "https://www.starlink.com/account/home"
        }

        # 2. DISCOVERY
        print("[*] Fetching IDs from service-lines...")
        r_ids = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=api_headers)
        if r_ids.status_code == 200:
            print("  [SUCCESS] IDs found.")
        else:
            print(f"  [-] service-lines failed: {r_ids.status_code} {r_ids.text}")
            return

        # 3. TELEMETRY QUERY
        url = "https://api.starlink.com/public/v2/telemetry/query"
        body = {
            "columnNamesByDeviceType": {
                "u": ["DeviceType", "UtcTimestampNs", "DeviceId", "PingLatencyMsAvg", "PingDropRateAvg"],
                "r": ["DeviceType", "UtcTimestampNs", "DeviceId", "Uptime", "PingLatencyMs"]
            }
        }
        print("[*] Hitting Query API...")
        r_api = client.post(url, headers=api_headers, json=body)
        print(f"  [HTTP] Status: {r_api.status_code}")
        if r_api.status_code == 200:
            print("  [SUCCESS] Received JSON:")
            print(json.dumps(r_api.json(), indent=2))
        else:
            print(f"  [-] Error: {r_api.text}")

    except Exception as e:
        print(f"  [-] Diagnostic Error: {e}")

if __name__ == "__main__":
    run_test()
