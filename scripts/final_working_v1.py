import httpx, re, json, sys, os, binascii
from pathlib import Path
from google.protobuf.json_format import MessageToDict

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "starlink_remote"))

try:
    from spacex.api.device.device_pb2 import Request, GetStatusRequest, Response
except ImportError:
    print("[-] Error: Could not import protobuf definitions.")
    sys.exit(1)

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'

def run_test():
    # Use the LATEST cookie provided by the user
    raw_cookie = "_ga=GA1.1.1075706988.1775039010; sx_selected_locale=en-US; __stripe_mid=d9c9227b-ce7c-4402-861b-13bdb5bc0151a605c4; Starlink.Com.Sso.CheckSession=CB586348F75F9D763DAD484E0D808C67; Starlink.Com.Sso=CfDJ8LtfW3omojlBhUQi_zkD2NTWXUPyI0ywIH9etIF4p_VZwLZDgD_14QUtq-yjXBi3O4F49MwRjveuHgwG0SQm-v8KTgSe58i-FRVL4eS1U9W1VIKpsEj2y6kG6vh8-HzUifvZxZ6IHCIOUUryLACFdmOucLjpf0PRbvwE8h4mOcOj2CAblZBYmXrnPJGw83Mm3tf3GrfcA1pnjw7eKHnDCppQvbUQxV_p9omfeSTo9kCUrw_FxZ9JhZkh9Qw7LLx_tzjaZ0LJLZdZRKkYnXRzdMbS7e_rruRl0rFllq8b3tWM781F3cf1QolYTqNJJ0Z3mBDJgjrqFB7Hg51pR1E0beE; starlink.com.account_number=ACC-5147187-41313-10; _ga_S07SYD5D4F=GS2.1.s1775233492$o19$g1$t1775235258$j60$l0$h0; Starlink.Com.Access.V1=CfDJ8LtfW3omojlBhUQi_zkD2NTu1hZRXGV26EP_rigyA75oq_QZiKtRy5hnhf9RbOwKG5jwOgEgMGXszfaFVHfDK7dbX17b5R-8pMtq9fdSDIw5c4wdR25bByEjmPyWDHBQ8QgRmUs2Zzx2huAmtkxzfDQAwxrN4iIVDjv6n77Ih3Sg-MOSq0vxhevkRKGDJWzLe7mKP8WPAmMDL6HP_Hg1SVAKB6VU7gMthzJKSAPbttVQYAXfh_Zd-yGU-nZKIXo1UuAE7dWUUQmPOBOPddo3W6RTjLz-03saBpoZ3BLlSFQ0GjFSvD7UsOzeyx5o8gd0ZnIKfp_06X9u1l11SqI0UAtKtx5k2vjmmK2TYZ96xiU4vUNVWetkZmLB18vfL_eZGn0BcXLL-XKbTKGphj8LlvgZE3WXQNf-K0CwzULN1qsW6cMqRa8olPDngoQn9and4Svjx5TIRWL1YPz7h9uHreSATG7iMEXO1eY7uF2j_W0WtSrX0K0im2jKiRAqCFSpnQgJltHIPrnG79NzN9Cv_MYEMaZEjh3b_X2mxtR30FCZ-oTiiEfsvTqQ4dsa9tYgJJH-9PhzTuFghqmtWVmfvYZU6AvHydJi82OtNaN5BkVF175qHfcP1VB-wb5bcShmKpB12N-sxHbl4iDjRmQJw6ro0HmTamgdry_wq5co8lVT-hxqBy-rd_8plRNCs4pKZ6kknAPDDIqFIyL0XQqZ62ezy0iuiUDWBO-YosXZZ5aUM2PZyU7_m7jBqXVrIQyQc0WHt4IvK7A_28cFZhkYDWaAUCE9pCoH7JUEOocvkml8cHkzLa8ZBzs5pFsrwK4-kVdBgCTd6nd1nsvCCtaj1OzNFo9Fe37LIPnFipobRw0Hd4dMUfA4zhYdCQtlhBhokIMV0ClvVBKLZFQakfQzTBf0R9u_B7LObGVE6XX8jTHbPaluQOz2HnGgdSc5b21V-UNe0GNwkdxia97fiHAt8gsDF2SzCxWu_suhBLcO4x2KbikJdlKJZhDSYiNdFoQh72S3sa-mfpngma0-JQoz6Vj7GA7-dch7-1_IBNI-AEupgIQ4Va8reyLQiirlKqzSCFj2ZfB1hZzTfbo-02Wb7d4GnoR4kMrpHRFUh9SXI4UOi7berLNRnOCPmMhxLsuYKYJJajn9lVGgUQeweWfKfAo0-YkHpRAzJ_xKcwVo36T1xZfw9uKwqjaEYSGBJjOGb1WLWSxaYI5NmF0NEIhxkBfHEXik56QEe5ZXJpWzcVR09vMLvfY0Wa1Kr4iZu278tMKa5cvzImnhthE0mHzkLPcMRz-P9SGrma"

    # Extract XSRF
    xsrf = ""
    xsrf_match = re.search(r'XSRF-TOKEN=([^;]+)', raw_cookie)
    if xsrf_match:
        xsrf = xsrf_match.group(1)
        print(f"[+] Found XSRF Token: {xsrf[:15]}...")

    client = httpx.Client(http2=True, follow_redirects=True)
    
    headers = {
        "User-Agent": UA,
        "cookie": raw_cookie,
        "origin": "https://www.starlink.com",
        "referer": "https://www.starlink.com/account/home",
        "x-xsrf-token": xsrf,
        "accept": "*/*",
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1"
    }

    # Use the IDs found in previous successful probe
    discovered = ["ut10588f9d-45017219-5815f472", "Router-0100000000000000008B65AD"]

    print("\n[*] Step 1: Telemetry Polling...")
    url = "https://www.starlink.com/api/SpaceX.API.Device.Device/Handle"
    
    for tid in discovered:
        print(f"\n>>> TARGET: {tid}")
        req = Request(target_id=tid, get_status=GetStatusRequest())
        ser = req.SerializeToString()
        frame = b'\x00' + len(ser).to_bytes(4, 'big') + ser
        
        try:
            res = client.post(url, headers=headers, content=frame)
            print(f"  [HTTP] {res.status_code} | Length: {len(res.content)}")
            
            if len(res.content) > 5:
                msg_len = int.from_bytes(res.content[1:5], 'big')
                out = Response()
                out.ParseFromString(res.content[5:5+msg_len])
                rt = out.WhichOneof('response')
                if rt:
                    print(f"  [SUCCESS] Received: {rt}")
                    rd = MessageToDict(getattr(out, rt), preserving_proto_field_name=True)
                    if 'downlink_throughput_bps' in rd:
                        print(f"    - Downlink: {round(float(rd['downlink_throughput_bps'])/1e6, 2)} Mbps")
                    if 'clients' in rd:
                        print(f"    - WiFi Clients: {len(rd['clients'])}")
                else:
                    print("  [-] Empty Response object.")
            else:
                print(f"  [-] Body too short: {binascii.hexlify(res.content)}")
        except Exception as e:
            print(f"  [-] Poll Error: {e}")

if __name__ == "__main__":
    run_test()
