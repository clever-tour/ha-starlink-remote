import httpx
import json

def main():
    with open("cookie.txt", "r") as f:
        cookie = f.read().strip()
    
    # Account from earlier ACC-5147187-41313-10
    acc = "ACC-5147187-41313-10"
    
    headers = {
        "accept": "application/json",
        "cookie": cookie,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    }
    
    # Discovery patterns for event logs
    urls = [
        f"https://api.starlink.com/webagg/v2/accounts/{acc}/service-alerts",
        f"https://api.starlink.com/webagg/v2/accounts/{acc}/outages",
        f"https://api.starlink.com/webagg/v2/accounts/{acc}/telemetry",
        "https://api.starlink.com/webagg/v2/accounts/service-alerts",
        "https://api.starlink.com/webagg/v2/accounts/telemetry/last-24h",
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
            except Exception as e:
                print(f"[-] Error: {e}")

    with open("scripts/webagg_events_probe.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
