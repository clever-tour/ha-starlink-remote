import httpx
import json
import os
import sys

def main():
    cookies_str = os.environ.get("STARLINK_COOKIE")
    if not cookies_str:
        print("[-] Error: STARLINK_COOKIE environment variable not set")
        sys.exit(1)
    
    # Use the inventory URL that worked before
    url = "https://www.starlink.com/api/web-inventory/v2/service-lines"
    
    headers = {
        "accept": "application/json",
        "cookie": cookies_str,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "origin": "https://www.starlink.com",
        "referer": "https://www.starlink.com/"
    }
    
    print(f"[*] Calling Inventory API...")
    
    try:
        resp = httpx.get(url, headers=headers, timeout=15.0)
        print(f"[DEBUG] HTTP Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            lines = data.get("serviceLines", [])
            if not lines:
                print("[-] No service lines found.")
                print(f"[DEBUG] Response: {json.dumps(data, indent=2)}")
                return

            print(f"\n[+] SUCCESS! Found {len(lines)} service lines:")
            for line in lines:
                print(f"  - Nickname:    {line.get('nickname')}")
                print(f"    DEVICE ID:    {line.get('starlinkId')}")
                # Check for other IDs
                for ut in line.get("userTerminals", []):
                    print(f"    UT ID:       {ut.get('userTerminalId')}")
                    for r in ut.get("routers", []):
                        print(f"    ROUTER ID:   {r.get('routerId')}")
        else:
            print(f"[-] API Error {resp.status_code}: {resp.text[:200]}")
            
    except Exception as e:
        print(f"[-] Discovery failed: {e}")

if __name__ == "__main__":
    main()
