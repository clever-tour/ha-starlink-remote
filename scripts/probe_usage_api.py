import httpx
import json
import os

def main():
    with open("cookie.txt", "r") as f:
        cookie = f.read().strip()
    
    # Extract account number from cookie if possible, or use the one we know
    # From Turn 18: ACC-5147187-41313-10
    account_number = "ACC-5147187-41313-10"
    
    headers = {
        "accept": "application/json",
        "cookie": cookie,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    }
    
    # Common data usage endpoints
    urls = [
        f"https://api.starlink.com/webagg/v2/accounts/{account_number}/data-usage",
        "https://api.starlink.com/webagg/v2/accounts/data-usage",
        "https://api.starlink.com/webagg/v2/accounts/service-lines", # Already tried
    ]
    
    results = {}
    with httpx.Client() as client:
        for url in urls:
            print(f"[*] Probing {url}...")
            try:
                resp = client.get(url, headers=headers, timeout=10.0)
                print(f"[*] Response: {resp.status_code}")
                if resp.status_code == 200:
                    results[url] = resp.json()
                    print(f"[+] SUCCESS for {url}")
                else:
                    print(f"[-] Failed: {resp.text[:100]}")
            except Exception as e:
                print(f"[-] Error: {e}")

    with open("scripts/usage_probe.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
