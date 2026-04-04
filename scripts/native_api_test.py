import httpx
import json
import sys
from pathlib import Path
from spacex.api.device.device_pb2 import Request, GetStatusRequest
from google.protobuf.json_format import MessageToDict

def main():
    # 1. Configuration from your SUCCESSFUL browser request
    url = "https://starlink.com/api/SpaceX.API.Device.Device/Handle"
    target_id = "ut10588f9d-45017219-5815f472"
    
    cookies_str = (
        "_ga=GA1.1.953080577.1775024709; sx_selected_locale=en-US; "
        "__stripe_mid=b03f6830-cac5-40a4-a8c8-4bfcfe177ce7c50625; "
        "Starlink.Com.Sso.CheckSession=2F9F62A6293F6D05F6BF32CA51196E31; "
        "Starlink.Com.Sso=CfDJ8LtfW3omojlBhUQi_zkD2NShbWZu1o7RdYKGO53tv7d0aP2HnRrQvg797cNmHnzD9jV4SyHwUfURsi7W-_xYjAsjW_s-9ecxeAQOcSw6DEqEs5ZKysbTXnsh0r3NW7-wzS-BXGJwfF3zwAYoYm-_3_jzylou2sgbD35AJVSY7bNm5ZiwpMExbAAP_JOZtaAy71GuZR_GuTmnQlKbI--C3E_1R_bSMxO-I-E4Z37GrWcbuHnVfaKjLt0XP2NGDRSQ_NSlc08CaYTtR5WLLZJ3DgJgZ7Vp9Tj_6t6B8j9EHNw2xNhv5Dj-n5zHJeTEgr-ZijpWnpURih77FFjcfD4yQFk; "
        "starlink.com.account_number=ACC-5147187-41313-10; "
        "_ga_S07SYD5D4F=GS2.1.s1775031155$o3$g0$t1775031155$j60$l0$h0; "
        "Starlink.Com.Access.V1=CfDJ8LtfW3omojlBhUQi_zkD2NSOk_RGv30gD_SB1XveAqZ9lKsRHt1pMKv_4rEwQDwTZTNUHARHxw_DkjITkQLgJDTwcbpRmMk0gYEuKXf9izNkHrJMqeX4Fsc6zsLVw-wEhnDTCywsKTCAECjv9Us9IuxjAhLWJpCfRhszdBM3OUBQtFp_7M86BdceR5wc2mPi7LGLuM8Y5O3K2Jr57i7DXLutoI4iXRSOkM730NBP731S3fRoPi7RJw-gKDgZ5VKVaKBgz5GnA_Fl0slTVrjazDVLInJtT3zvRrMq0bykQFbQr2yOwtJRT8MzsLm1eoNpcJEM1CK3kteiay_1Tj3tLaIg82vm5LJS87M6BIlweRxi7rzk2toXb_mHdNCpXjRL4tLzSvFE3ysCqVgw5oImqR60V6vBtpwe2cBjcvdWb71uNH2FNI3732EnBz8bQ93eoMc9ls_Wahary9QyO4n0sf7RNU-MUAChTmzuCWeeW3kXNqP5QtV17VyRYvPNKiEVZUsQ45B5IwlgKjqRdjwwOn4yOxmc6w7R60xXyLESXDpsZNjlswn4_nm-lVWXktjNBU4Qhmu7Lp1dH2UjE7F4v_rlGSdEOfTVwpST9-Ciwepd7SD5OIjcgYTdlH36DinTYmsNeGQaOSYY3KrOlX2Wy7aEioOafOhwe1e-q1ieHdGzmm1q7wtRB7GiVgcW8HPvXjh_21JaO0d8GyuglbqdfDh8ufFvUCFTpxd1axSTOtWOWktJoL-v_edh9ob-H8xpSCVcZ1Kw5MIze7MDgN0fYw-WqZy-rXkFeEUOafr_p2eZM92DkSR3FlnegVUXB1YmAKrzDrr79BhGQpyXn5da7tpyoZ4xf98CZv2sdP7FP2ltEscsFXvlC9If41eczSpGiUBfANeKES0ep1fe1OCJDJth8J-RfhAn8ymF_grCM0Eoyi-E96kzhhxFhZ7Pz6oS7i9W2DA--SYAUY-qgFwLRdPqiB5kmsR8gQSBU-raanG4Ptqdm0gBtsdpU8FeGaSAduW5GRf9bhnTk-rpN_DluOqm-K5qVttqdK2diLJDGlZWvRevQkoJ93goAUPHjGfRk_NKgqWqzt-iJs8CGf6rgOIsdRVRU8luDA57zItKqfbNDqMvE8UbFDyydslzyfpVaWZ5pEhIrPkA451ovSeypanX-f2FrRWD35OTukKqEPJ1Bids8toDjBOsO5D37gZvNBPHhqv-FJHBuFpuZXeGHaV-t-gPJ3PWIkZRifaK-ymlD19SJzsu5qTgkE0tGOq55eq7l4ArrcVvGAZu1AvYtj0ioX0z9DaPdsm4NBMEZ21AYOjOPW4Qakrh9yiI3P-04XlBzD6FnjOPYL7OqhIARGD-Iw2U2D6PfodIWDZypCNLM4APIIzO-CV_YIJneumnoQ0AIKAapry2dv1OM9OOyTt6Wwru_ytaRQQUeAbgpfVBlgOAnQcfZUFUzL_mMnUaGF-9XegGxGmbro01wmvaqwNIa06j8AwexP16x0zarMsoIkZoei-UDhctAOdbWTlSULMHftyKO0E_alLF0hLVDtXueaLsm5JNbLC8LL2BMeOyAcBW31uaVSDWK8snom0MHNIPILRmlwelmzDyNsb86Vxtsc0i-enn0UR6YVosjmjrwXlr40vq1bzWyNBLGVpumxMdqBWUXLH_9tdvHeUEVHbPVWDgk0s7zM7QrQYkxp34y0YPfuLyH6mx0zRGzJbWaSURAnl-8KUi8wgdDQhidrtrO1ttWr2pibEVz0DDlPwsOUwD8RdF1-cF4vzHTeMPu_6CZyglwlkBJGqvNWjFdsbmvk9V4EzLSLA-RVcJMqEk8yPpvsoUAAoytSvbjdH_Wu7EVMZ8axJofakrCJs8wsb94MuG-rVl3gktLFvjqgYs06Y6XWODtl7I4GcEv23R2Les_K45HmC4_A-0MpKk-MiONTzWZnElWepdNd8Ra5uQNn6zjdupMmmaSvjV-6crjKeUTFcTOQtKB2jW6Kut2gP4WgdtMCqSmzCSfnSa6I_PPHsHwOvzOnrImLYr9KcX0czxt0FxCaSxtgRYxOOX-8AgIxKR6ZTrpFypcg8zG9dJ8i2HWnnk7Gwuvvte76wpe68l3h_tX5LLWpFCH4gRcV5oN8kf2gPyqbLZNnbjfyDGAk06yYoNxQIK4BLp-ClUSw8I8JL4TmPFEenX2cbdXoFHigt4_gre1UN2JNWkIwzPY6vEv0WR0MRxZXqaCMgKeWPjg31eOxHf1KZY-WPipgf1_OcS6h5_h92med9sACV2dSwrmGce3N3L2RQxK7_kpEJxfKuU5kWp7Eg_GHuxOsKdz6IsjStSBMF7R5D3ZfFrMq5xBXazphMcX2xuFTrE8YIeyKLTDERXwJh93anF8SY-6gLOFuAmkrf-A62rSuGRKoZ-a-Vs9ZXSxQDcyI4U4SX-5YwIN0A5BHfiIE3Q4-J1_kBrZSazycKSZaOpAu1TvO6kqMbL492OPmnkL-1WE1jje-wLN3AISlIWm-W77bIWwzZPANJ-aqT1nXDNzjAN94kNMpyvFeRTmHJO22L9LeaL9TOTnHJPDD9Isr6pUumw4SdCl1cutipBEelminlbva8xaeQc9A2tQfYLo66gnwXVk3vnD-ap9YjJotcBVaA_GnHxcWOsI6SvGAF10Iscdobtj6ETlr3rg7rOF07f-YwoG_fI3DfHPQ9pG0jdAKgKeQ3Rcg0UDUq7DLZz5PjwtcVQvbFxBBaGkcv9MxY15Vx4Z-z8q0wWWMCSWw5yaFxE7AeFvSGxM8fX4ZsZZ4JkZITddji119Tg-a_kZdtUR-ga7urlSjrBdC3Rm-MlBF5LIMzct-g0E_fWNHRjIos8LXzKp2Xtetz-dbO6dN-zPAVSXZc1abQbpSNoGlu2_Kd0KOUc7DPiQHNzRpYwpobQQiDyHwnCk4hC_QO3f0lXY7c0usnW-QSEUyHXVe9RDrcVxdjHtaXb72CU8OgmATl4kH-Wbi6ofhkyfk-cTpntswhaMzoEF_FaL19rQ3EL3TSLO4_yECkEE_tH4bZAQzcfx5cJynvXcKOXIFbAivKLKm6kaYs4VU_D24B0T9aCP6C-3RsXL3C2CzfROhDAJUhlkiu97FC1R3oQ4P_qdZBuC27sXdLH-KVLnqv0Zautd_f66_tVE2eApGwYWNauxjOgYFkywUbofX5g5sYlO_j-1w"
    )
    
    headers = {
        "accept": "*/*",
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "cookie": cookies_str,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "origin": "https://starlink.com",
        "referer": "https://starlink.com/account/home"
    }

    # 2. Build the Protobuf request
    req = Request(target_id=target_id, get_status=GetStatusRequest())
    serialized = req.SerializeToString()
    
    # Wrap in gRPC-Web binary frame
    # 0x00 (flags) + 4-byte big-endian length + payload
    frame = b'\x00' + len(serialized).to_bytes(4, 'big') + serialized

    print(f"[*] Sending NATIVE API probe to {url}...")
    print(f"[*] Using Target ID: {target_id}")

    try:
        with httpx.Client(http2=True) as client:
            resp = client.post(url, headers=headers, content=frame, timeout=10.0)
            
            print(f"[DEBUG] HTTP Status: {resp.status_code}")
            
            # Check for gRPC error in headers
            grpc_status = resp.headers.get("grpc-status", "0")
            grpc_msg = resp.headers.get("grpc-message", "OK")
            
            print(f"[DEBUG] gRPC Status: {grpc_status} ({grpc_msg})")
            
            if resp.status_code == 200 and grpc_status == "0":
                print("[+] SUCCESS! The Starlink backend accepted the native request.")
                
                # Parse gRPC-Web response frame
                # Response is also framed: 5 bytes header + body
                if len(resp.content) > 5:
                    data_len = int.from_bytes(resp.content[1:5], 'big')
                    data_payload = resp.content[5:5+data_len]
                    
                    from spacex.api.device.device_pb2 import Response
                    dish_resp = Response()
                    dish_resp.ParseFromString(data_payload)
                    
                    print("\n[+] Dish Status Data:")
                    print(json.dumps(MessageToDict(dish_resp.dish_get_status, always_print_fields_with_no_presence=True), indent=2))
                return 0
            else:
                print(f"[-] Request rejected by backend.")
                return 1
                
    except Exception as e:
        print(f"[-] Native request failed: {e}")
        return 1

if __name__ == "__main__":
    main()
