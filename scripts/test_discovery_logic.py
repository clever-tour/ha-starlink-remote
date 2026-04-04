import httpx
import re
import os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    if not os.path.exists("cookie.txt"):
        print("[-] cookie.txt not found.")
        return

    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    
    # 1. Prime session and get fresh cookie
    print("[*] Priming session from starlink.com/account/home...")
    headers = {
        "User-Agent": UA,
        "cookie": raw_cookie
    }
    try:
        r = client.get("https://www.starlink.com/account/home", headers=headers)
        print(f"  [HTTP] Status: {r.status_code}")
        
        # Look for selectedDevice= in the page content or links
        print("[*] Searching for selectedDevice= in HTML...")
        matches = re.findall(r'selectedDevice=([A-Fa-f0-9-]+)', r.text)
        print(f"  [+] Found in home: {matches}")
        
        # Also try service-line page as mentioned by user
        print("[*] Trying starlink.com/account/service-line...")
        # Note: The user said click 'your subscription' which might be this URL
        r2 = client.get("https://www.starlink.com/account/service-line", headers=headers)
        print(f"  [HTTP] Status: {r2.status_code}")
        matches2 = re.findall(r'selectedDevice=([A-Fa-f0-9-]+)', r2.text)
        print(f"  [+] Found in service-line: {matches2}")
        
        # Look for the ut or Router- patterns too
        uts = re.findall(r"ut[a-f0-9-]{26,36}", r2.text)
        routers = re.findall(r"Router-[A-Fa-f0-9]{24}", r2.text)
        print(f"  [+] Found UTs: {uts}")
        print(f"  [+] Found Routers: {routers}")

    except Exception as e:
        print(f"  [-] Error: {e}")

if __name__ == "__main__":
    run_test()
