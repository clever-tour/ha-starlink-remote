import httpx, re, json, os, sys, time

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    with open("cookie.txt", "r") as f:
        raw_cookie = f.read().strip()

    sys.path.insert(0, os.path.join(os.getcwd(), "custom_components/starlink_remote"))
    from spacex.api.device.device_pb2 import Request, Response, DishGetStatusRequest, DishGetHistoryRequest
    from google.protobuf.json_format import MessageToDict

    client = httpx.Client(http2=True, follow_redirects=True)
    
    xsrf = ""
    match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if match: xsrf = match.group(1)

    headers = {
        "User-Agent": UA, "cookie": raw_cookie, "x-xsrf-token": xsrf,
        "content-type": "application/grpc-web+proto", "x-grpc-web": "1"
    }

    url = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"
    tid = "ut10588f9d-45017219-5815f472"

    # Priming
    client.get("https://www.starlink.com/account/home", headers={"User-Agent": UA, "cookie": raw_cookie})
    time.sleep(0.1)

    print(f"[*] Polling Dish: {tid}")
    
    # 1. Get Status
    print("  >>> DishGetStatusRequest...")
    req = Request(target_id=tid, dish_get_status=DishGetStatusRequest())
    ser = req.SerializeToString()
    frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
    res = client.post(url, headers=headers, content=frame)
    if res.status_code == 200 and len(res.content) > 5:
        msg_len = int.from_bytes(res.content[1:5], 'big')
        out = Response()
        out.ParseFromString(res.content[5:5+msg_len])
        rt = out.WhichOneof('response')
        if rt:
            data = MessageToDict(getattr(out, rt), preserving_proto_field_name=True)
            with open("dish_status.json", "w") as f: json.dump(data, f, indent=2)
            print("  [SUCCESS] Status saved to dish_status.json")

    # 2. Get History
    print("\n  >>> DishGetHistoryRequest...")
    req = Request(target_id=tid, dish_get_history=DishGetHistoryRequest())
    ser = req.SerializeToString()
    frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
    res = client.post(url, headers=headers, content=frame)
    if res.status_code == 200 and len(res.content) > 5:
        msg_len = int.from_bytes(res.content[1:5], 'big')
        out = Response()
        out.ParseFromString(res.content[5:5+msg_len])
        rt = out.WhichOneof('response')
        if rt:
            data = MessageToDict(getattr(out, rt), preserving_proto_field_name=True)
            with open("dish_history.json", "w") as f: json.dump(data, f, indent=2)
            print("  [SUCCESS] History saved to dish_history.json")

if __name__ == "__main__":
    run_test()
