import httpx, re, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    headers = {"User-Agent": UA, "cookie": raw_cookie}
    
    try:
        r = client.get("https://www.starlink.com/account/home", headers=headers)
        print(f"[HTTP] Status: {r.status_code}")
        # Search for telemetry or usage patterns
        match = re.search(r'telemetry', r.text, re.I)
        if match: print("[+] Found 'telemetry' in HTML.")
        
        match2 = re.search(r'usage', r.text, re.I)
        if match2: print("[+] Found 'usage' in HTML.")
        
        # Search for any large JSON blocks
        scripts = re.findall(r'<script>(.*?)</script>', r.text, re.S)
        for s in scripts:
            if 'window.__PRELOADED_STATE__' in s:
                print("[+] Found PRELOADED_STATE script.")
                # Save it for analysis
                with open("scripts/preloaded_state.json.txt", "w") as f_json:
                    f_json.write(s)
                    
    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    run_test()
