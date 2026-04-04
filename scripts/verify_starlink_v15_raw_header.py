import httpx, re, json, sys, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    # Extract XSRF from string
    xsrf = ""
    xsrf_match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if xsrf_match: xsrf = xsrf_match.group(1)

    client = httpx.Client(http2=True, follow_redirects=True)
    
    # RAW HEADER INJECTION (Bypass Cookie Jar)
    headers = {
        "User-Agent": UA,
        "cookie": raw_cookie,
        "x-xsrf-token": xsrf,
        "origin": "https://www.starlink.com",
        "referer": "https://www.starlink.com/account/home",
        "accept": "application/json, text/plain, */*"
    }

    print("[*] Testing Discovery with RAW Cookie Header...")
    try:
        r = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=headers)
        print(f"  [API] Status: {r.status_code}")
        if r.status_code == 200:
            print("  [SUCCESS] DISCOVERY WORKED!")
            print(f"  [DATA] {r.text[:500]}")
        else:
            # Try the basic auth endpoint
            r2 = client.get("https://api.starlink.com/auth-rp/auth/user", headers=headers)
            print(f"  [AUTH-RP] Status: {r2.status_code}")
    except Exception as e:
        print(f"  [-] Error: {e}")

if __name__ == "__main__":
    run_test()
