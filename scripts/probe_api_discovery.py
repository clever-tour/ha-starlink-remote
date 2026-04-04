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

    url = "https://api.starlink.com/webagg/v2/accounts/service-lines"
    
    print(f"[*] Probing: {url}")
    try:
        r = client.get(url, headers=headers)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(json.dumps(data, indent=2))
            
            # Check for IDs in the JSON
            ids = set()
            for res in data.get("content", {}).get("results", []):
                for ut in res.get("userTerminals", []):
                    uid = ut.get("userTerminalId")
                    if uid: ids.add(f"ut{uid}")
                    for rtr in ut.get("routers", []):
                        rid = rtr.get("routerId")
                        if rid: ids.add(f"Router-{rid}")
            print(f"\n[+] Found IDs in API: {ids}")
        else:
            print(f"  Error: {r.text}")

    except Exception as e:
        print(f"  Error: {e}")

if __name__ == "__main__":
    run_test()
