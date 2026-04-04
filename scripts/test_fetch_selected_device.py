import os
import httpx
import re
import json

def fetch_selected_device():
    cookie_path = "cookie.txt"
    if not os.path.exists(cookie_path):
        print(f"[-] Error: {cookie_path} not found")
        return

    with open(cookie_path, "r") as f:
        cookie_str = f.read().strip()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "cookie": cookie_str,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.starlink.com",
        "Referer": "https://www.starlink.com/account/home"
    }

    url = "https://www.starlink.com/api/auth/user"
    
    print(f"[*] Fetching from {url}...")
    
    with httpx.Client(http2=True) as client:
        response = client.get(url, headers=headers)
        
    if response.status_code != 200:
        print(f"[-] Failed. Status: {response.status_code}")
        return

    try:
        data = response.json()
        print("[+] Successfully fetched JSON.")
        
        # Search for prefixed IDs
        raw_text = response.text
        routers = re.findall(r"Router-[A-Fa-f0-9]+", raw_text)
        dishes = re.findall(r"ut[a-f0-9-]+", raw_text)
        
        if routers: print(f"  [+] Found Routers: {list(set(routers))}")
        if dishes: print(f"  [+] Found Dishes: {list(set(dishes))}")
        
        # Target specific values requested by user
        targets = ["Router-0100000000000000008B65AD", "ut10588f9d-45017219-5815f472"]
        print("\n[*] Checking for specific target IDs:")
        found_any = False
        for t in targets:
            if t in raw_text:
                print(f"  [+] FOUND: {t}")
                found_any = True
            else:
                print(f"  [-] NOT FOUND: {t}")

        # Look for "selectedDevice"
        print("\n[*] Searching for 'selectedDevice' key:")
        def find_val(obj, key, path=""):
            results = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    current_path = f"{path}.{k}" if path else k
                    if k == key: results.append((current_path, v))
                    results.extend(find_val(v, key, current_path))
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    current_path = f"{path}[{i}]"
                    results.extend(find_val(item, key, current_path))
            return results

        selected = find_val(data, "selectedDevice")
        if selected:
            for path, val in selected:
                print(f"  [+] Found 'selectedDevice' at {path}: {val}")
        else:
            print("  [-] 'selectedDevice' key not found in JSON.")

    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    fetch_selected_device()
