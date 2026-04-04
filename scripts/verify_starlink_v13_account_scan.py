import httpx, re, json, sys, os, binascii
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "starlink_remote"))

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    headers = {"User-Agent": UA, "cookie": raw_cookie}

    # 1. Capture fresh XSRF and Account Info
    print("[*] Scanning Account Info...")
    r = client.get("https://api.starlink.com/auth-rp/auth/user", headers=headers)
    print(f"  [Auth] Status: {r.status_code}")
    
    xsrf = client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')
    if not xsrf:
        m = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
        if m: xsrf = m.group(1)
    
    headers['x-xsrf-token'] = xsrf

    # 2. Robust Discovery via multiple endpoints
    print("\n[*] Step 1: Discovery Scan...")
    discovered = set()
    
    endpoints = [
        "https://api.starlink.com/webagg/v2/accounts/service-lines",
        "https://api.starlink.com/webagg/v2/accounts/service-lines?include_inactive=true"
    ]
    
    for url in endpoints:
        try:
            r = client.get(url, headers=headers)
            print(f"  [API] {url} -> Status {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                # Dump the raw discovery to see what's actually there
                print(f"  [RAW] {json.dumps(data)[:200]}...")
                for res in data.get("content", {}).get("results", []):
                    for ut in res.get("userTerminals", []):
                        uid = ut.get("userTerminalId")
                        if uid: discovered.add(f"ut{uid}")
                        for rtr in ut.get("routers", []):
                            rid = rtr.get("routerId")
                            if rid: discovered.add(f"Router-{rid}")
        except Exception as e:
            print(f"  [-] Error at {url}: {e}")

    print(f"\n[+] FINAL DISCOVERED IDS: {discovered}")
    
    if not discovered:
        print("[!] ACCOUNT SCAN RETURNED NO DEVICES. This is the root cause of zero sensors.")

if __name__ == "__main__":
    run_test()
