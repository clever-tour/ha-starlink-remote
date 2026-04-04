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

    urls = [
        f"https://api.starlink.com/webagg/v2/accounts/service-lines/{sl}/usage",
        f"https://api.starlink.com/webagg/v2/accounts/service-lines/{sl}/telemetry",
    ]

    for url in urls:
        print(f"[*] Probing: {url}")
        try:
            r = client.get(url, headers=headers)
            print(f"  Status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                with open("usage_probe.json", "w") as f: json.dump(data, f, indent=2)
                print(f"  [SUCCESS] Data saved. Sample: {str(data)[:200]}...")
            else:
                print(f"  Error: {r.text[:200]}")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    run()
