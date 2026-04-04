import httpx, re, json, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    headers = {"User-Agent": UA, "cookie": raw_cookie}
    
    xsrf = ""
    match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if match: xsrf = match.group(1)
    headers["x-xsrf-token"] = xsrf

    uid = "ut10588f9d-45017219-5815f472"
    url = f"https://www.starlink.com/account/service-line?selectedDevice={uid}"
    
    print(f"[*] Visiting: {url}")
    try:
        r = client.get(url, headers=headers)
        print(f"  [HTTP] Status: {r.status_code}")
        
        # Look for JSON in scripts
        scripts = re.findall(r'<script type="application/json">(.*?)</script>', r.text, re.S)
        print(f"  [+] Found {len(scripts)} JSON scripts.")
        for i, s in enumerate(scripts):
            try:
                data = json.loads(s)
                # Look for device or telemetry data
                str_data = json.dumps(data)
                if uid in str_data:
                    print(f"    [!] Script {i} contains Device ID!")
                    print(json.dumps(data, indent=2)[:1000] + "...")
            except: pass
            
        # Also look for window.__PRELOADED_STATE__
        state_match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*({.*?});', r.text)
        if state_match:
            print("  [+] Found window.__PRELOADED_STATE__")
            with open("scripts/service_line_state.json.txt", "w") as fs:
                fs.write(state_match.group(1))
            
    except Exception as e:
        print(f"  [-] Error: {e}")

if __name__ == "__main__":
    run_test()
