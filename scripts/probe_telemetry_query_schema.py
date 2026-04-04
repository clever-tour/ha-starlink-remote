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

    ids = ["ut10588f9d-45017219-5815f472", "Router-0100000000000000008B65AD"]
    url = "https://api.starlink.com/public/v2/telemetry/query"
    
    scenarios = [
        {"name": "List of IDs", "body": ids},
        {"name": "Object with deviceIds", "body": {"deviceIds": ids}},
        {"name": "Object with ids", "body": {"ids": ids}},
        {"name": "Object with deviceId", "body": {"deviceId": ids[0]}},
    ]

    for s in scenarios:
        print(f"[*] Probing: {s['name']}")
        try:
            r = client.post(url, headers=headers, json=s['body'])
            print(f"  [HTTP] Status: {r.status_code}")
            if r.status_code == 200:
                print(f"    [SUCCESS] Received JSON:")
                print(json.dumps(r.json(), indent=2))
                break
            else:
                print(f"    [-] Response: {r.text[:200]}")
        except Exception as e:
            print(f"    [-] Error: {e}")

if __name__ == "__main__":
    run_test()
