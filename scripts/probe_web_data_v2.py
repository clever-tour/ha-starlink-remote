import httpx, re, json, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run():
    with open("cookie.txt", "r") as f: raw_cookie = f.read().strip()
    client = httpx.Client(http2=True, follow_redirects=True)
    headers = {"User-Agent": UA, "cookie": raw_cookie}
    
    # Primary dashboard
    print("[*] Fetching account/home...")
    r = client.get("https://www.starlink.com/account/home", headers=headers)
    
    # Search for all JSON script tags
    scripts = re.findall(r'<script id="[^"]+" type="application/json">(.*?)</script>', r.text, re.S)
    for i, s in enumerate(scripts):
        try:
            data = json.loads(s)
            if any(k in s.lower() for k in ['outage', 'event', 'alert', 'interference']):
                print(f"  [+] Found potential data in script {i}")
                with open(f"web_data_{i}.json", "w") as f: json.dump(data, f, indent=2)
        except: pass

    # Also check service-line page specifically
    print("[*] Fetching account/service-line...")
    r = client.get("https://www.starlink.com/account/service-line", headers=headers)
    scripts = re.findall(r'<script id="[^"]+" type="application/json">(.*?)</script>', r.text, re.S)
    for i, s in enumerate(scripts):
        try:
            data = json.loads(s)
            if any(k in s.lower() for k in ['outage', 'event', 'alert', 'interference']):
                print(f"  [+] Found potential data in service-line script {i}")
                with open(f"sl_web_data_{i}.json", "w") as f: json.dump(data, f, indent=2)
        except: pass

if __name__ == "__main__": run()
