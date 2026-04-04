import httpx, re, json, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run():
    with open("cookie.txt", "r") as f: raw_cookie = f.read().strip()
    client = httpx.Client(http2=True, follow_redirects=True)
    
    # Session priming
    client.get("https://www.starlink.com/account/home", headers={"User-Agent": UA, "cookie": raw_cookie})
    xsrf = client.cookies.get('XSRF-TOKEN', domain='.starlink.com', default='')
    client.get("https://api.starlink.com/auth-rp/auth/user", headers={"User-Agent": UA, "cookie": raw_cookie, "x-xsrf-token": xsrf})

    fresh_cookie = "; ".join([f"{c.name}={c.value}" for c in client.cookies.jar])
    headers = {
        "User-Agent": UA, "cookie": fresh_cookie or raw_cookie, "x-xsrf-token": xsrf,
        "content-type": "application/json"
    }

    # Fetch SL ID
    r_sl = client.get("https://api.starlink.com/webagg/v2/accounts/service-lines", headers=headers)
    sl_num = r_sl.json()['content']['results'][0]['serviceLineNumber']

    # The Android app often uses 'webagg/v2/service-lines/{id}/telemetry/query'
    # to get aggregated event counts.
    url = f"https://api.starlink.com/webagg/v2/service-lines/{sl_num}/telemetry/query"
    print(f"[*] Probing Telemetry Query: {url}")
    
    # Common query for events/outages
    body = {
        "columnNamesByDeviceType": {
            "u": ["UtcTimestampNs", "OutageCause", "OutageDurationNs"],
            "r": ["UtcTimestampNs", "WifiInterferenceLevel", "PublicIpAddress"]
        }
    }

    try:
        r = client.post(url, headers=headers, json=body)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            with open("webagg_telemetry_query.json", "w") as f: json.dump(data, f, indent=2)
            print(f"  [SUCCESS] Data received and saved.")
        else:
            print(f"  Error: {r.text[:200]}")
    except Exception as e:
        print(f"  Error: {e}")

if __name__ == "__main__":
    run()
