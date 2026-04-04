import httpx, re, json, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run():
    with open("cookie.txt", "r") as f: raw_cookie = f.read().strip()
    client = httpx.Client(http2=True, follow_redirects=True)
    
    xsrf = ""
    match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if match: xsrf = match.group(1)

    headers = {
        "User-Agent": UA, "cookie": raw_cookie, "x-xsrf-token": xsrf,
        "origin": "https://www.starlink.com", "referer": "https://www.starlink.com/account/home"
    }

    # SL ID
    sl = "SL-1991965-88036-90"

    # Try service line page telemetry
    print("[*] Probing SL page telemetry...")
    r = client.get(f"https://www.starlink.com/account/service-line/{sl}", headers=headers)
    
    # Check for __PRELOADED_STATE__
    state_match = re.search(r'__PRELOADED_STATE__\s*=\s*({.*?});', r.text)
    if state_match:
        print("[+] Found __PRELOADED_STATE__")
        state = state_match.group(1)
        if 'outage' in state.lower(): print("    - Contains 'outage'")
        if 'interference' in state.lower(): print("    - Contains 'interference'")
        if 'interruption' in state.lower(): print("    - Contains 'interruption'")
        
        # Save a snippet
        with open("sl_page_state.json", "w") as f: f.write(state)

if __name__ == "__main__": run()
