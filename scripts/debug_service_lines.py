import httpx
import re
import os
import json

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    if not os.path.exists("cookie.txt"):
        print("[-] cookie.txt not found.")
        return

    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    
    headers = {
        "User-Agent": UA,
        "cookie": raw_cookie
    }
    
    # Extract XSRF from cookie string for headers
    xsrf = ""
    match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if match:
        xsrf = match.group(1)
        headers["x-xsrf-token"] = xsrf

    print("[*] Hitting service-lines API...")
    try:
        r = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=headers)
        print(f"  [HTTP] Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(json.dumps(data, indent=2))
        else:
            print(f"  [-] Error: {r.text}")

    except Exception as e:
        print(f"  [-] Error: {e}")

if __name__ == "__main__":
    run_test()
