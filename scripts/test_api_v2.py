import httpx
import json
from pathlib import Path

def main():
    # Load cookies from the golden session
    session_file = list(Path(".golden_auth_session").glob("*.json"))[0]
    with open(session_file, "r") as f:
        cookies_data = json.load(f)
    
    cookies_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies_data])
    
    url = "https://www.starlink.com/api/web-inventory/v2/service-lines"
    headers = {
        "accept": "application/json",
        "cookie": cookies_str,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print(f"[*] Testing Starlink API connection (service-lines)...")
    try:
        resp = httpx.get(url, headers=headers, timeout=10.0)
        print(f"[+] HTTP Status: {resp.status_code}")
        
        if resp.status_code == 200:
            try:
                data = resp.json()
                print(f"[+] SUCCESS! Found {len(data.get('serviceLines', []))} service lines.")
                print(json.dumps(data, indent=2))
            except json.JSONDecodeError:
                print(f"[-] Received HTTP 200 but failed to parse JSON.")
                print(f"[DEBUG] Headers: {dict(resp.headers)}")
                print(f"[DEBUG] Body: {repr(resp.text)}")
        else:
            print(f"[-] API Error: {resp.status_code}")
            print(f"[DEBUG] Body: {repr(resp.text)}")
    except Exception as e:
        print(f"[-] Connection failed: {e}")

if __name__ == "__main__":
    main()
