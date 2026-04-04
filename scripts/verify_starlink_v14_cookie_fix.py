import httpx, re, json, sys, os, binascii
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "starlink_remote"))

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    # Use a persistent client to maintain cross-subdomain affinity
    client = httpx.Client(http2=True, follow_redirects=True)
    
    # CRITICAL: Manually set cookies for BOTH domains
    for part in raw_cookie.split(';'):
        if '=' in part:
            k, v = part.strip().split('=', 1)
            client.cookies.set(k, v, domain='.starlink.com')
            client.cookies.set(k, v, domain='api.starlink.com')

    # 1. Establish XSRF
    print("[*] Priming Session...")
    r = client.get("https://api.starlink.com/auth-rp/auth/user", headers={"User-Agent": UA})
    xsrf = client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')
    if not xsrf:
        m = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
        if m: xsrf = m.group(1)

    headers = {
        "User-Agent": UA,
        "x-xsrf-token": xsrf,
        "origin": "https://www.starlink.com",
        "referer": "https://www.starlink.com/account/home"
    }

    # 2. DISCOVERY
    print("\n[*] Step 1: Discovery Scan...")
    try:
        url = "https://api.starlink.com/webagg/v2/accounts/service-lines"
        r = client.get(url, headers=headers)
        print(f"  [API] Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"  [SUCCESS] Discovery Data Found!")
            for res in data.get("content", {}).get("results", []):
                for ut in res.get("userTerminals", []):
                    print(f"    - Found UT: ut{ut.get('userTerminalId')}")
                    for rtr in ut.get("routers", []):
                        print(f"    - Found Router: Router-{rtr.get('routerId')}")
    except Exception as e:
        print(f"  [-] Error: {e}")

if __name__ == "__main__":
    run_test()
