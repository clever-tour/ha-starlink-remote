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
    url = "https://api.starlink.com/webagg/v2/accounts/service-lines?limit=10&page=0&isConverting=false&serviceAddressId=&onlyActive=false&searchString=&onlyNoUts=false"
    
    headers = {
        "accept": "application/json",
        "cookie": cookies_str,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "origin": "https://www.starlink.com",
        "referer": "https://www.starlink.com/"
    }
    
    print(f"[*] Calling ServiceLines API...")
    
    try:
        resp = httpx.get(url, headers=headers, timeout=15.0)
        print(f"[DEBUG] HTTP Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("content", {}).get("results", [])
            if not results:
                print("[-] No service lines found.")
                print(f"[DEBUG] Response: {json.dumps(data, indent=2)}")
                return

            print(f"\n[+] SUCCESS! Found {len(results)} service lines:")
            for res in results:
                print(f"  - Nickname:    {res.get('nickname')}")
                for ut in res.get("userTerminals", []):
                    print(f"    UT ID:       {ut.get('userTerminalId')}")
                    for r in ut.get("routers", []):
                        print(f"    ROUTER ID:   {r.get('routerId')}")
        else:
            print(f"[-] API Error {resp.status_code}: {resp.text}")
            
    except Exception as e:
        print(f"[-] Discovery failed: {e}")

if __name__ == "__main__":
    main()
