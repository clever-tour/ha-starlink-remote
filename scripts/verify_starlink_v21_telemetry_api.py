import httpx, re, json, sys, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    
    # 1. DISCOVERY via service-line page
    print("[*] Accessing subscription page for discovery...")
    headers = {"User-Agent": UA, "cookie": raw_cookie}
    try:
        r = client.get("https://www.starlink.com/account/service-line", headers=headers)
        print(f"  [HTTP] Status: {r.status_code}")
        
        # Look for selectedDevice= in the HTML
        ids = re.findall(r'selectedDevice=([A-Fa-f0-9-]+)', r.text)
        print(f"  [+] Found selectedDevice IDs: {ids}")
        
        # Also look for the standard patterns just in case
        routers = re.findall(r"Router-[A-Fa-f0-9]{24}", r.text)
        uts = re.findall(r"ut[a-f0-9-]{8}-[a-f0-9-]{36}", r.text) # Broaden ut pattern
        if not uts:
            uts = re.findall(r"ut[a-f0-9-]{26,36}", r.text)
            
        all_ids = set(ids + routers + uts)
        print(f"  [+] All potential IDs: {all_ids}")

        # 2. TELEMETRY API TEST
        print("\n[*] Testing Public Telemetry API (Query)...")
        # Try hitting the telemetry endpoint with session cookies
        # Note: Bearer token is often extracted from the 'Starlink.Com.Access.V1' cookie
        
        xsrf = client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')
        if not xsrf:
            m = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
            if m: xsrf = m.group(1)

        api_headers = {
            "User-Agent": UA, "cookie": raw_cookie, "x-xsrf-token": xsrf,
            "Content-Type": "application/json",
            "origin": "https://www.starlink.com", "referer": "https://www.starlink.com/account/home"
        }
        
        # The 'query' API typically takes a body, but let's try a simple POST
        query_url = "https://www.starlink.com/api/public/v2/telemetry/query"
        # Optional: try to see if it works without body (fetching all)
        try:
            r_api = client.post(query_url, headers=api_headers, json={})
            print(f"  [API Query] Status: {r_api.status_code}")
            if r_api.status_code == 200:
                print("  [SUCCESS] Received Telemetry Data:")
                print(json.dumps(r_api.json(), indent=2)[:1000] + "...")
            else:
                print(f"  [-] Error: {r_api.text}")
        except Exception as e:
            print(f"  [-] API Error: {e}")

    except Exception as e:
        print(f"  [-] Diagnostic Error: {e}")

if __name__ == "__main__":
    run_test()
