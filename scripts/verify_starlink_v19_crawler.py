import httpx, re, json

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    headers = {"User-Agent": UA, "cookie": raw_cookie}

    print("[*] Crawling Account Dashboard for Live IDs...")
    try:
        r = client.get("https://www.starlink.com/account/home", headers=headers)
        if r.status_code == 200:
            # Method 1: Preloaded State Regex
            state = re.search(r'window\.__PRELOADED_STATE__\s*=\s*({.*?});', r.text)
            if state:
                print("  [+] Found Preloaded State!")
                # Search for any ID-like strings in the JSON
                # Dish IDs: ut[a-f0-9-]{36}
                # Router IDs: [A-F0-9]{24}
                ids = re.findall(r'"([A-Fa-f0-9]{24})"', state.group(1))
                uts = re.findall(r'"(ut[a-f0-9-]{26,36})"', state.group(1))
                print(f"  [+] Found Serial-like strings: {ids}")
                print(f"  [+] Found UT-like strings: {uts}")
            else:
                print("  [-] Preloaded state not found in HTML.")
                # Method 2: Global Search in full HTML
                all_ids = re.findall(r'Router-[A-Fa-f0-9]{24}', r.text)
                all_uts = re.findall(r'ut[a-f0-9-]{26,36}', r.text)
                print(f"  [+] Global Search Found: {all_ids + all_uts}")
    except Exception as e:
        print(f"  [-] Crawl Error: {e}")

if __name__ == "__main__":
    run_test()
