import httpx, re, json, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    headers = {"User-Agent": UA, "cookie": raw_cookie}
    
    try:
        r = client.get("https://www.starlink.com/account/home", headers=headers)
        state_match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*({.*?});', r.text)
        if state_match:
            print("[+] Found PRELOADED_STATE")
            # The state is often huge, let's just look for keys
            state_text = state_match.group(1)
            # Try to parse just the top level keys if possible
            try:
                # Need to handle potential JS escapes or unquoted keys if any, 
                # but usually it's clean JSON
                data = json.loads(state_text)
                print(f"Keys: {list(data.keys())}")
                
                # Check for 'account' or 'userTerminals'
                if 'account' in data:
                    print("Account data found.")
                if 'userTerminals' in data:
                    print("UT data found.")
                
                # Look for usage or telemetry
                for k in data.keys():
                    if 'usage' in k.lower() or 'telemetry' in k.lower() or 'status' in k.lower():
                        print(f"Potential telemetry key: {k}")
                        # print(json.dumps(data[k], indent=2)[:500])
            except Exception as e:
                print(f"JSON Parse error: {e}")
                # Fallback: regex search for patterns
                print("Searching via regex...")
                if 'usage' in state_text.lower(): print("Found 'usage' in state text.")
                if 'telemetry' in state_text.lower(): print("Found 'telemetry' in state text.")
        else:
            print("[-] PRELOADED_STATE not found")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_test()
