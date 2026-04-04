import httpx, re, binascii

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    # Extract XSRF
    xsrf = ""
    xsrf_match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if xsrf_match: xsrf = xsrf_match.group(1)

    client = httpx.Client(http2=True, follow_redirects=True)
    
    # RAW PROTOBUF CONSTRUCTION (Field 13 = target_id, Field 1001 = get_status)
    # Field 13 (target_id) -> Wire Type 2 (String)
    # Field 1001 (get_status) -> Wire Type 2 (Message) -> Length 0 (Empty sub-message)
    
    def build_raw_request(tid):
        # 1. target_id (Field 13, Type 2) -> (13 << 3) | 2 = 0x6A
        tid_bytes = tid.encode()
        p1 = b'\x6a' + bytes([len(tid_bytes)]) + tid_bytes
        
        # 2. get_status (Field 1001, Type 2) -> (1001 << 3) | 2 = 0x3E9 << 3 | 2 = 0x1F4A
        # Field 1001 is encoded as varint: \xca\x3e
        p2 = b'\xca\x3e\x00' # ca 3e 00 = Field 1001, Wire 2, Length 0
        
        payload = p1 + p2
        # gRPC-Web framing
        return b'\x00' + len(payload).to_bytes(4, 'big') + payload

    headers = {
        "User-Agent": UA,
        "cookie": raw_cookie,
        "x-xsrf-token": xsrf,
        "origin": "https://www.starlink.com",
        "referer": "https://www.starlink.com/account/home",
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1"
    }

    url = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"
    targets = ["Router-0100000000000000008B65AD", "ut10588f9d-45017219-5815f472"]

    for tid in targets:
        print(f"\n>>> RAW TEST: {tid}")
        frame = build_raw_request(tid)
        try:
            res = client.post(url, headers=headers, content=frame)
            print(f"  [HTTP] {res.status_code} | Bytes: {len(res.content)}")
            if len(res.content) > 0:
                print(f"  [SUCCESS] RECEIVED DATA: {binascii.hexlify(res.content[:32])}...")
        except Exception as e:
            print(f"  [-] Error: {e}")

if __name__ == "__main__":
    run_test()
