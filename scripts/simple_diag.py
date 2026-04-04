import httpx
import json
import os
import sys

def main():
    cookie = os.environ.get("STARLINK_COOKIE")
    # Inventory API
    url = "https://www.starlink.com/api/web-inventory/v2/service-lines"
    
    headers = {
        "cookie": cookie,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    }
    
    with httpx.Client() as client:
        resp = client.get(url, headers=headers)
        print(f"Status: {resp.status_code}")
        print(f"Text Sample: {resp.text[:500]}")
        
        # Webagg API
        url2 = "https://api.starlink.com/webagg/v2/accounts/service-lines"
        resp2 = client.get(url2, headers=headers)
        print(f"\nWebagg Status: {resp2.status_code}")
        print(f"Webagg Text: {resp2.text[:500]}")

if __name__ == "__main__":
    main()
