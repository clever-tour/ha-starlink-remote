import httpx, re, json

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    
    # Extract XSRF
    xsrf = ""
    xsrf_match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if xsrf_match: xsrf = xsrf_match.group(1)

    headers = {
        "User-Agent": UA,
        "cookie": raw_cookie,
        "x-xsrf-token": xsrf,
        "accept": "application/json"
    }

    print("[*] Testing Account List API...")
    try:
        r = client.get("https://api.starlink.com/webagg/v2/accounts", headers=headers)
        print(f"  [Accounts] Status: {r.status_code}")
        if r.status_code == 200:
            print(f"  [DATA] {r.text}")
    except Exception as e:
        print(f"  [-] Error: {e}")

if __name__ == "__main__":
    run_test()
