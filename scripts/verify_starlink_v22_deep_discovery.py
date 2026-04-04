import httpx, re, json, sys, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    headers = {"User-Agent": UA, "cookie": raw_cookie}
    
    xsrf = ""
    match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if match:
        xsrf = match.group(1)
        headers["x-xsrf-token"] = xsrf

    # 1. DISCOVERY via HTML
    print("[*] Accessing subscription page for discovery...")
    try:
        r = client.get("https://www.starlink.com/account/home", headers=headers)
        print(f"  [Home Page] Status: {r.status_code}")
        
        # Method A: window.__PRELOADED_STATE__
        print("  [*] Searching for Preloaded State...")
        state_match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*({.*?});', r.text)
        if state_match:
            try:
                state = json.loads(state_match.group(1))
                print("    [+] Successfully parsed Preloaded State.")
                # Look for device lists
                # Usually in 'account' or 'userTerminal' keys
                for key in state.keys():
                    if 'device' in key.lower() or 'terminal' in key.lower():
                        print(f"    [+] Found potential key: {key}")
            except: pass
        
        # Method B: Links
        print("  [*] Searching for selectedDevice in links...")
        matches = re.findall(r'selectedDevice=([A-Fa-f0-9-]+)', r.text)
        print(f"    [+] Found in links: {matches}")
        
        # Method C: service-lines API (the most reliable so far)
        print("\n[*] Trying service-lines API...")
        r_lines = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=headers)
        if r_lines.status_code == 200:
            data = r_lines.json()
            ids = set()
            for res in data.get("content", {}).get("results", []):
                for ut in res.get("userTerminals", []):
                    uid = ut.get("userTerminalId")
                    if uid: ids.add(f"ut{uid}")
                    for rtr in ut.get("routers", []):
                        rid = rtr.get("routerId")
                        if rid: ids.add(f"Router-{rid}")
            print(f"  [Discovery] Status: {r_lines.status_code} | Found IDs: {ids}")
        else:
            print(f"  [-] service-lines failed: {r_lines.status_code} {r_lines.text}")

        # 2. TELEMETRY API TEST
        print("\n[*] Testing Public Telemetry API (Query)...")
        query_url = "https://www.starlink.com/api/public/v2/telemetry/query"
        # Let's try to get a Bearer token from the 'Starlink.Com.Access.V1' cookie
        # Many of these Starlink internal APIs use the Access token as a Bearer
        
        access_token = re.search(r'Starlink.Com.Access.V1=([^;]+)', raw_cookie)
        if access_token:
            bearer = access_token.group(1)
            # Authorization headers
            bearer_headers = {
                "User-Agent": UA,
                "Authorization": f"Bearer {bearer}",
                "Content-Type": "application/json",
                "x-xsrf-token": xsrf
            }
            # Try a simple time-range query
            try:
                # The 'query' API typically requires device IDs or timestamps
                # Let's try a very simple query object
                # Some versions take: {"deviceIds": ["..."], "start": ..., "end": ...}
                r_api = client.post(query_url, headers=bearer_headers, json={})
                print(f"  [Bearer Query] Status: {r_api.status_code}")
                if r_api.status_code == 200:
                    print(json.dumps(r_api.json(), indent=2)[:500] + "...")
                else:
                    print(f"  [-] Bearer Query failed: {r_api.text}")
            except Exception as e:
                print(f"  [-] API Error: {e}")

    except Exception as e:
        print(f"  [-] Diagnostic Error: {e}")

if __name__ == "__main__":
    run_test()
