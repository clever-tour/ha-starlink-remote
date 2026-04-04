import httpx, re, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    client = httpx.Client(http2=True, follow_redirects=True)
    headers = {"User-Agent": UA, "cookie": raw_cookie}
    
    try:
        r = client.get("https://www.starlink.com/account/home", headers=headers)
        print(f"[HTTP] Status: {r.status_code}")
        print(r.text[:5000])
    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    run_test()
