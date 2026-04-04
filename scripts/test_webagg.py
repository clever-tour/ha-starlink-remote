import httpx
import json
import os

def main():
    with open("cookie.txt", "r") as f:
        cookie = f.read().strip()
    
    url = "https://api.starlink.com/webagg/v2/accounts/service-lines"
    
    headers = {
        "accept": "application/json",
        "cookie": cookie,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    }
    
    print("[*] Fetching service lines via Webagg API...")
    with httpx.Client() as client:
        resp = client.get(url, headers=headers)
        print(f"[*] Response: {resp.status_code}")
        if resp.status_code == 200:
            print("[SUCCESS] Data received!")
            print(json.dumps(resp.json(), indent=2))
        else:
            print(f"[-] Error: {resp.text}")

if __name__ == "__main__":
    main()
