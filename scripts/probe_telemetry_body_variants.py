import httpx, re, json, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    with httpx.Client(http2=True, follow_redirects=True) as client:
        for part in raw_cookie.split(';'):
            if '=' in part:
                k, v = part.strip().split('=', 1)
                client.cookies.set(k, v, domain='.starlink.com')

        xsrf = client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')
        common_headers = {
            "User-Agent": UA, "x-xsrf-token": xsrf,
            "origin": "https://www.starlink.com", "referer": "https://www.starlink.com/account/home"
        }

        # Prime
        client.get("https://www.starlink.com/account/home", headers=common_headers)
        client.get("https://api.starlink.com/auth-rp/auth/user", headers=common_headers)

        uid = "ut10588f9d-45017219-5815f472"
        rid = "Router-0100000000000000008B65AD"
        url = "https://api.starlink.com/public/v2/telemetry/query"
        
        variants = [
            {"deviceIds": [uid, rid]},
            {"device_ids": [uid, rid]},
            {"ids": [uid, rid]},
            [uid, rid],
            {"batchSize": 1},
            {"limit": 1}
        ]

        for v in variants:
            print(f"[*] Variant: {v}")
            r = client.post(url, headers=common_headers, json=v)
            print(f"  [HTTP] {r.status_code} | {r.text[:100]}")
            if r.status_code == 200:
                print("  [SUCCESS] Data found!")
                print(json.dumps(r.json(), indent=2)[:500])
                break

if __name__ == "__main__":
    run_test()
