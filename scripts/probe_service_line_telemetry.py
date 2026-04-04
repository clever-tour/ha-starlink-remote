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

    sl = "SL-1991965-88036-90"
    base = f"https://api.starlink.com/webagg/v2/accounts/service-lines/{sl}"
    
    endpoints = [
        f"{base}/telemetry",
        f"{base}/status",
        f"{base}/usage",
        f"{base}/details",
    ]

    for url in endpoints:
        print(f"[*] Probing: {url}")
        try:
            r = client.get(url, headers=headers)
            print(f"  [HTTP] Status: {r.status_code}")
            if r.status_code == 200:
                print(f"    [SUCCESS] Received JSON:")
                print(json.dumps(r.json(), indent=2)[:1000] + "...")
            else:
                print(f"    [-] Response: {r.text[:200]}")
        except Exception as e:
            print(f"    [-] Error: {e}")

if __name__ == "__main__":
    run_test()
