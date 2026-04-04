import httpx
import json
import os
import sys

def main():
    cookies_str = os.environ.get("STARLINK_COOKIE")
    if not cookies_str:
        print("[-] Error: STARLINK_COOKIE environment variable not set")
        sys.exit(1)
    
    # Discovery URL from starlink-client
    url = "https://api.starlink.com/webagg/v2/accounts/service-lines?limit=10&page=0&isConverting=false&serviceAddressId=&onlyActive=false&searchString=&onlyNoUts=false"
    
    headers = {
        "accept": "application/json",
        "cookie": cookies_str,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print(f"[*] Calling ServiceLines API to find your REAL hardware IDs...")
    
    try:
        resp = httpx.get(url, headers=headers, timeout=10.0)
        
        print(f"[DEBUG] HTTP Status: {resp.status_code}")
        
        if resp.status_code == 200:
            try:
                data = resp.json()
                print("[+] Successfully parsed JSON response.")
                
                # Print the raw JSON (formatted) for debugging
                # print(json.dumps(data, indent=2))
                
                results = data.get("content", {}).get("results", [])
                if not results:
                    print("[-] No service lines found in 'content.results'.")
                    print(f"[DEBUG] Full Response: {json.dumps(data, indent=2)}")
                    return

                print(f"\n[+] SUCCESS! Found {len(results)} service lines:")
                for res in results:
                    nickname = res.get("nickname", "N/A")
                    print(f"  - Nickname:    {nickname}")
                    
                    user_terminals = res.get("userTerminals", [])
                    for ut in user_terminals:
                        ut_id = ut.get("userTerminalId")
                        print(f"    UT ID:       {ut_id}")
                        
                        # The router ID is usually what we need for the integration
                        routers = ut.get("routers", [])
                        for r in routers:
                            router_id = r.get("routerId")
                            print(f"    ROUTER ID:   {router_id}  <-- USE THIS!")
                    
                    print("-" * 40)
            except Exception as json_err:
                print(f"[-] Failed to parse JSON: {json_err}")
                print(f"[DEBUG] Raw Response: {resp.text[:1000]}")
        else:
            print(f"[-] API Error {resp.status_code}: {resp.text[:500]}")
            
    except Exception as e:
        print(f"[-] Discovery failed: {e}")

if __name__ == "__main__":
    main()
