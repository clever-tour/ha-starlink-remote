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
        "Content-Type": "application/json",
        "origin": "https://www.starlink.com", "referer": "https://www.starlink.com/account/home"
    }

    url = "https://www.starlink.com/api/public/v2/telemetry/stream"
    
    body = {
        "batchSize": 1,
        "maxLingerMs": 1000
    }

    print("[*] Hitting Stream API...")
    try:
        r = client.post(url, headers=headers, json=body)
        print(f"  [HTTP] Status: {r.status_code}")
        if r.status_code == 200:
            print("  [SUCCESS] Data:")
            print(json.dumps(r.json(), indent=2)[:2000])
        else:
            print(f"  [-] Error: {r.text}")
    except Exception as e:
        print(f"  [-] Error: {e}")

if __name__ == "__main__":
    run_test()
