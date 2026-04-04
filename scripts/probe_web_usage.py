import httpx, re, json, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    headers = {"User-Agent": UA, "cookie": raw_cookie}
    
    try:
        r = client.get("https://www.starlink.com/account/home", headers=headers)
        # Search for any script containing data
        scripts = re.findall(r'<script id="[^"]+" type="application/json">(.*?)</script>', r.text, re.S)
        for s in scripts:
            try:
                data = json.loads(s)
                if 'usage' in s.lower() or 'telemetry' in s.lower():
                    print(f"[+] Found potential data script.")
                    print(json.dumps(data, indent=2)[:1000])
            except: pass
            
        # Standard Next.js / React preloaded state patterns
        state_match = re.search(r'__PRELOADED_STATE__\s*=\s*({.*?});', r.text)
        if state_match:
            print("[+] Found __PRELOADED_STATE__")
            if 'usage' in state_match.group(1).lower():
                print("    - Contains usage data!")
                # Extract usage specifically if possible
                usage_match = re.search(r'"usage":({.*?})', state_match.group(1))
                if usage_match:
                    print(usage_match.group(1)[:500])
        
        props_match = re.search(r'__NEXT_DATA__\s*=\s*({.*?});', r.text)
        if props_match:
            print("[+] Found __NEXT_DATA__")
            data = json.loads(props_match.group(1))
            # Search for usage in nested props
            def find_usage(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k == 'usage': return v
                        res = find_usage(v)
                        if res: return res
                elif isinstance(obj, list):
                    for item in obj:
                        res = find_usage(item)
                        if res: return res
                return None
            
            usage = find_usage(data)
            if usage:
                print("    [SUCCESS] Found usage data in NEXT_DATA!")
                print(json.dumps(usage, indent=2))

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_test()
