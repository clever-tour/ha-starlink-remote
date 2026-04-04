import httpx, re, os

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run():
    with open("cookie.txt", "r") as f: raw_cookie = f.read().strip()
    client = httpx.Client(http2=True, follow_redirects=True)
    headers = {"User-Agent": UA, "cookie": raw_cookie}
    
    r = client.get("https://www.starlink.com/account/home", headers=headers)
    with open("account_home.html", "w") as f: f.write(r.text)
    print(f"HTML saved to account_home.html. Size: {len(r.text)} bytes")

if __name__ == "__main__": run()
