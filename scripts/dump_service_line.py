import httpx, re, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    headers = {"User-Agent": UA, "cookie": raw_cookie}
    
    try:
        # User said click 'your subscription' which is /account/service-line
        r = client.get("https://www.starlink.com/account/service-line", headers=headers)
        print(f"Status: {r.status_code}")
        # Search for IDs specifically
        print("--- SEARCH RESULTS ---")
        for match in re.findall(r'selectedDevice=[A-Fa-f0-9-]+', r.text):
            print(f"Found match: {match}")
        
        # Look for the user terminal ID pattern specifically
        for match in re.findall(r'ut[a-z0-9-]{26,36}', r.text):
            print(f"Found UT: {match}")
            
        # Look for router ID pattern
        for match in re.findall(r'Router-[A-Fa-f0-9]{24}', r.text):
            print(f"Found Router: {match}")

        # Dump a bit of the HTML around where these usually are
        print("\n--- HTML SNIPPET ---")
        idx = r.text.find("serviceLine")
        if idx != -1:
            print(r.text[idx-500:idx+2000])
        else:
            print("Could not find 'serviceLine' string in HTML.")
            # Search for PRELOADED_STATE
            idx2 = r.text.find("__PRELOADED_STATE__")
            if idx2 != -1:
                print(r.text[idx2:idx2+2000])

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_test()
