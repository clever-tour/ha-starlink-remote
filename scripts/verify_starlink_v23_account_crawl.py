import httpx, re, json, sys, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    headers = {"User-Agent": UA, "cookie": raw_cookie}
    
    xsrf = ""
    match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if match:
        xsrf = match.group(1)
        headers["x-xsrf-token"] = xsrf

    print("[*] Accessing subscription page...")
    try:
        r = client.get("https://www.starlink.com/account/home", headers=headers)
        print(f"  [Home Page] Status: {r.status_code}")
        
        # Search for IDs in the HTML (they might be in JS objects)
        ids = set(re.findall(r'ut[a-f0-9-]{36}', r.text))
        routers = set(re.findall(r'Router-[A-Fa-f0-9]{24}', r.text))
        selected = set(re.findall(r'selectedDevice=([A-Fa-f0-9-]+)', r.text))
        print(f"  [+] Found UTs: {ids}")
        print(f"  [+] Found Routers: {routers}")
        print(f"  [+] Found Selected: {selected}")
        
        # Look for the subscription link specifically
        # User said: click 'your subscription' when language is set to 'English'
        # Let's search for the link that contains /service-line
        service_links = re.findall(r'href=["\']([^"\']+/service-line\?[^"\']+)["\']', r.text)
        print(f"  [+] Found service-line links: {service_links}")
        for link in service_links:
            # Expand relative link
            if link.startswith('/'): link = "https://www.starlink.com" + link
            print(f"    [*] Visiting: {link}")
            r2 = client.get(link, headers=headers)
            print(f"      [HTTP] Status: {r2.status_code}")
            # Look for IDs in this page too
            sub_ids = set(re.findall(r'ut[a-f0-9-]{36}', r2.text))
            sub_routers = set(re.findall(r'Router-[A-Fa-f0-9]{24}', r2.text))
            sub_selected = set(re.findall(r'selectedDevice=([A-Fa-f0-9-]+)', r2.text))
            print(f"      [+] Found UTs: {sub_ids}")
            print(f"      [+] Found Routers: {sub_routers}")
            print(f"      [+] Found Selected: {sub_selected}")

    except Exception as e:
        print(f"  [-] Diagnostic Error: {e}")

if __name__ == "__main__":
    run_test()
