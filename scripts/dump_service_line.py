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

    r = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=headers)
    if r.status_code == 200:
        with open("service_lines_full.json", "w") as f: json.dump(r.json(), f, indent=2)
        print("[SUCCESS] service_lines_full.json saved.")

if __name__ == "__main__": run()
