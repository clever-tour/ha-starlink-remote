import httpx
import json
import os
import sys

def main():
    cookies_str = os.environ.get("STARLINK_COOKIE")
    if not cookies_str:
        print("[-] Error: STARLINK_COOKIE environment variable not set")
        sys.exit(1)
    
    # Discovery URL
    url = "https://starlink.com/api/web-inventory/v2/service-lines"
    
    headers = {
        "accept": "application/json",
        "cookie": cookies_str,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print(f"[*] Calling ServiceLines API to find your REAL hardware IDs...")
    
    try:
        resp = httpx.get(url, headers=headers, timeout=10.0)
        
        if resp.status_code == 200:
            try:
                data = resp.json()
            except Exception as json_err:
                print(f"[-] Failed to parse JSON: {json_err}")
                print(f"[DEBUG] Raw Response: {resp.text}")
                return
            
            lines = data.get("serviceLines", [])
            if not lines:
                print("[-] No service lines found. Check your cookie.")
                print(f"[DEBUG] Raw Response: {resp.text}")
                return

            print(f"\n[+] SUCCESS! Found {len(lines)} service lines:")
            for line in lines:
                print(f"  - Nickname:    {line.get('nickname', 'N/A')}")
                print(f"    DEVICE ID:    {line.get('starlinkId')}  <-- USE THIS!")
                print(f"    Account:      {line.get('accountNumber')}")
                print("-" * 40)
        else:
            print(f"[-] API Error {resp.status_code}: {resp.text}")
            
    except Exception as e:
        print(f"[-] Discovery failed: {e}")

if __name__ == "__main__":
    main()
