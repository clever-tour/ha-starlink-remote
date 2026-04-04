import httpx, re, json, os, sys

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    sys.path.insert(0, os.path.join(os.getcwd(), "custom_components/starlink_remote"))
    from spacex.api.device.device_pb2 import Request, GetStatusRequest, Response
    from google.protobuf.json_format import MessageToDict

    client = httpx.Client(http2=True, follow_redirects=True)
    
    xsrf = ""
    match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if match: xsrf = match.group(1)

    headers = {
        "User-Agent": UA, "cookie": raw_cookie, "x-xsrf-token": xsrf,
        "origin": "https://www.starlink.com", "referer": "https://www.starlink.com/account/home",
        "content-type": "application/grpc-web+proto", "x-grpc-web": "1", "accept": "*/*"
    }

    url = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"
    
    # Priming call
    client.get("https://www.starlink.com/account/home", headers={"User-Agent": UA, "cookie": raw_cookie})
    client.get("https://api.starlink.com/auth-rp/auth/user", headers={"User-Agent": UA, "cookie": raw_cookie, "x-xsrf-token": xsrf})

    ids = ["ut10588f9d-45017219-5815f472", "Router-0100000000000000008B65AD"]

    for tid in ids:
        print(f"\n[*] Polling: {tid}")
        req = Request(target_id=tid, get_status=GetStatusRequest())
        ser = req.SerializeToString()
        frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
        
        try:
            res = client.post(url, headers=headers, content=frame)
            print(f"  HTTP: {res.status_code} | Bytes: {len(res.content)}")
            if res.status_code == 200 and len(res.content) > 5:
                msg_len = int.from_bytes(res.content[1:5], 'big')
                out = Response()
                out.ParseFromString(res.content[5:5+msg_len])
                rt = out.WhichOneof('response')
                if rt:
                    print(f"  [SUCCESS] Response Type: {rt}")
                    data = MessageToDict(getattr(out, rt), preserving_proto_field_name=True)
                    print(json.dumps(data, indent=2)[:500] + "...")
            else:
                print(f"  [-] Error: {res.text[:200]}")
        except Exception as e:
            print(f"  [-] Error: {e}")

if __name__ == "__main__":
    run_test()
