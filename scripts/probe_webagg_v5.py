import httpx, re, json, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run():
    with open("cookie.txt", "r") as f: raw_cookie = f.read().strip()
    client = httpx.Client(http2=True, follow_redirects=True)
    client.get("https://www.starlink.com/account/home", headers={"User-Agent": UA, "cookie": raw_cookie})
    xsrf = client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')
    client.get("https://api.starlink.com/auth-rp/auth/user", headers={"User-Agent": UA, "cookie": raw_cookie, "x-xsrf-token": xsrf})

    fresh_cookie = "; ".join([f"{c.name}={c.value}" for c in client.cookies.jar])
    headers = {"User-Agent": UA, "cookie": fresh_cookie or raw_cookie, "x-xsrf-token": xsrf}

    sl = "SL-1991965-88036-90"

    urls = [
        f"https://api.starlink.com/webagg/v2/service-lines/{sl}/status",
        f"https://api.starlink.com/webagg/v2/service-lines/{sl}/details",
        f"https://api.starlink.com/webagg/v2/service-lines/{sl}/events",
        f"https://api.starlink.com/webagg/v2/service-lines/{sl}/usage-summary",
    ]

    for url in urls:
        print(f"[*] Probing: {url}")
        r = client.get(url, headers=headers)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            print(f"  [SUCCESS] Data: {json.dumps(r.json(), indent=2)[:500]}")

if __name__ == "__main__": run()
