import os
import httpx
import re
import json

def main():
    cookie_path = "cookie.txt"
    if not os.path.exists(cookie_path):
        print(f"[-] Error: {cookie_path} not found")
        return

    with open(cookie_path, "r") as f:
        cookie_str = f.read().strip()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "cookie": cookie_str,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # URL to fetch (the main dashboard which has preloaded state)
    url = "https://www.starlink.com/account/home"
    
    print(f"[*] Fetching from {url}...")
    
    found_strings = set()
    
    try:
        with httpx.Client(http2=True, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            
            if resp.status_code == 200:
                content = resp.text
                
                # 1. Look for selectedDevice in the preloaded state or JS
                # Regex to find "selectedDevice": "..."
                matches = re.findall(r'["\']selectedDevice["\']\s*:\s*["\']([^"\']+)["\']', content)
                for m in matches:
                    found_strings.add(m)
                
                # 2. Look for the specific patterns user sees in their URL bar
                # Router- prefixed IDs
                routers = re.findall(r"Router-[A-Fa-f0-9]{24}", content)
                for r in routers:
                    found_strings.add(r)
                
                # ut prefixed IDs (usually ut + UUID)
                dishes = re.findall(r"ut[a-f0-9-]{36}", content)
                for d in dishes:
                    found_strings.add(d)

                # 3. Specifically check if the two target strings you mentioned exist in the raw source
                targets = ["Router-0100000000000000008B65AD", "ut10588f9d-45017219-5815f472"]
                for t in targets:
                    if t in content:
                        found_strings.add(t)
            else:
                print(f"[-] Fetch failed with status: {resp.status_code}")
                
    except Exception as e:
        print(f"[-] Error during fetch: {e}")

    # Fallback to local parsing of the service_lines_response.json if available
    # to reconstruct what the UI would show
    service_lines_path = "scripts/service_lines_response.json"
    if os.path.exists(service_lines_path):
        print(f"[*] Parsing local cache: {service_lines_path}")
        try:
            with open(service_lines_path, "r") as f:
                data = json.load(f)
                results = data.get("content", {}).get("results", [])
                for res in results:
                    for ut in res.get("userTerminals", []):
                        ut_id = ut.get("userTerminalId")
                        if ut_id: found_strings.add(f"ut{ut_id}")
                        for r in ut.get("routers", []):
                            r_id = r.get("routerId")
                            if r_id: found_strings.add(f"Router-{r_id}")
        except: pass

    print("\n" + "="*40)
    print("RESULTS: Found selectedDevice candidates")
    print("="*40)
    
    expected = ["Router-0100000000000000008B65AD", "ut10588f9d-45017219-5815f472"]
    
    if not found_strings:
        print("[-] No matching strings found.")
    else:
        for s in sorted(list(found_strings)):
            match_status = "✓ MATCH" if s in expected else ""
            print(f"  [+] {s} {match_status}")

    print("\n[*] Script execution finished.")

if __name__ == "__main__":
    main()
