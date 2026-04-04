import httpx, re, json, os, sys

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run():
    with open("cookie.txt", "r") as f: raw_cookie = f.read().strip()
    sys.path.insert(0, os.path.join(os.getcwd(), "custom_components/starlink_remote"))
    from spacex.api.device.device_pb2 import Request, Response, GetStatusRequest
    
    client = httpx.Client(http2=True)
    xsrf = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie).group(1)
    headers = {"User-Agent": UA, "cookie": raw_cookie, "x-xsrf-token": xsrf, "content-type": "application/grpc-web+proto", "x-grpc-web": "1"}
    
    url = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"
    tid = "ut10588f9d-45017219-5815f472"
    
    req = Request(target_id=tid, get_status=GetStatusRequest())
    ser = req.SerializeToString()
    frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
    res = client.post(url, headers=headers, content=frame)
    print(f"Status: {res.status_code} | Len: {len(res.content)}")
    
    if len(res.content) > 5:
        out = Response()
        out.ParseFromString(res.content[5:5+int.from_bytes(res.content[1:5], 'big')])
        print(f"WhichOneOf: {out.WhichOneof('response')}")
        # print(out)

if __name__ == "__main__": run()
