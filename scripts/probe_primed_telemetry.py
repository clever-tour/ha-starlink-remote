import httpx, re, json, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    
    xsrf = ""
    match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if match: xsrf = match.group(1)

    headers = {
        "User-Agent": UA, "cookie": raw_cookie, "x-xsrf-token": xsrf,
        "origin": "https://www.starlink.com", "referer": "https://www.starlink.com/account/home"
    }

    # 1. Get IDs
    print("[*] Getting IDs from service-lines...")
    r = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=headers)
    if r.status_code != 200:
        print(f"  [-] Failed: {r.text}")
        return
    
    data = r.json()
    ut_ids = []
    for res in data.get("content", {}).get("results", []):
        for ut in res.get("userTerminals", []):
            uid = ut.get("userTerminalId")
            if uid: ut_ids.append(uid)

    print(f"  [+] Found UT IDs: {ut_ids}")

    # 2. Prime session for each UT
    for uid in ut_ids:
        print(f"\n[*] Priming for: {uid}")
        prime_url = f"https://www.starlink.com/account/service-line?selectedDevice={uid}"
        r_prime = client.get(prime_url, headers=headers)
        print(f"  [Prime] Status: {r_prime.status_code}")
        
        # Update cookies from response
        new_cookies = "; ".join([f"{c.name}={c.value}" for c in client.cookies.jar])
        headers["cookie"] = new_cookies
        
        # 3. Try Telemetry API
        print(f"  [*] Probing Telemetry API for {uid}...")
        # Try both subdomains
        for base in ["https://api.starlink.com", "https://www.starlink.com"]:
            api_url = f"{base}/api/public/v2/telemetry/query"
            try:
                # Based on the readme, it might return all devices if body is batch-like
                r_api = client.post(api_url, headers=headers, json={"batchSize": 1, "maxLingerMs": 100})
                print(f"    [API {base}] Status: {r_api.status_code}")
                if r_api.status_code == 200:
                    print(f"      [SUCCESS] Received data.")
                    print(json.dumps(r_api.json(), indent=2)[:500])
                    return # Done!
            except: pass

if __name__ == "__main__":
    run_test()
