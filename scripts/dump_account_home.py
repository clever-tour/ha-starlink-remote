import httpx, re, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    headers = {"User-Agent": UA, "cookie": raw_cookie}
    
    try:
        r = client.get("https://www.starlink.com/account/home", headers=headers)
        print(f"Status: {r.status_code}")
        
        # Search for subscription links
        print("--- LINKS ---")
        for match in re.findall(r'href=["\']([^"\']+)["\']', r.text):
            if 'subscription' in match.lower() or 'service-line' in match.lower():
                print(f"Found potential link: {match}")

        # Search for IDs
        print("\n--- IDS ---")
        for match in re.findall(r'ut[a-z0-9-]{26,36}', r.text):
            print(f"Found UT: {match}")
        for match in re.findall(r'Router-[A-Fa-f0-9]{24}', r.text):
            print(f"Found Router: {match}")
        for match in re.findall(r'selectedDevice=[A-Fa-f0-9-]+', r.text):
            print(f"Found selectedDevice: {match}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_test()
