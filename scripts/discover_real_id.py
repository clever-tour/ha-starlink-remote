import httpx
import json
import sys
from spacex.api.device.device_pb2 import Request, GetStatusRequest

def main():
    # Use the verified working API2 cookies
    cookies_str = (
        "_ga=GA1.1.953080577.1775024709; sx_selected_locale=en-US; __stripe_mid=b03f6830-cac5-40a4-a8c8-4bfcfe177ce7c50625; Starlink.Com.Sso.CheckSession=2F9F62A6293F6D05F6BF32CA51196E31; Starlink.Com.Sso=CfDJ8LtfW3omojlBhUQi_zkD2NShbWZu1o7RdYKGO53tv7d0aP2HnRrQvg797cNmHnzD9jV4SyHwUfURsi7W-_xYjAsjW_s-9ecxeAQOcSw6DEqEs5ZKysbTXnsh0r3NW7-wzS-BXGJwfF3zwAYoYm-_3_jzylou2sgbD35AJVSY7bNm5ZiwpMExbAAP_JOZtaAy71GuZR_GuTmnQlKbI--C3E_1R_bSMxO-I-E4Z37GrWcbuHnVfaKjLt0XP2NGDRSQ_NSlc08CaYTtR5WLLZJ3DgJgZ7Vp9Tj_6t6B8j9EHNw2xNhv5Dj-n5zHJeTEgr-ZijpWnpURih77FFjcfD4yQFk; starlink.com.account_number=ACC-5147187-41313-10; __stripe_sid=c55bb2f3-b616-4bdb-8f90-822b958d31abe29197; Starlink.Com.Access.V1=CfDJ8LtfW3omojlBhUQi_zkD2NRC9_XO117VckKXPtAC4vIbfVugrjZEZ68bIIV2wqTRwabhi6fwU_FvyJKc4Q-_JNrdUP0g5XgwDdY-S-3pj7CIu4hvlfsgEtT7euTMRsQzh5VYKCgYDQv9aKSNzGVHMFlAJX6U8y0sz_4JpxfvPE_HzyNbtruswBiOwiW193tzKpMPNAodZ3n0OiQeQ951GbgwsWdchtKfR08pOJ5sqBfQLy6cUhPxy1nOEN2W6QW7sfxnzQ2qKuI7PHN_SltI19I_EKbQbRBBRHmuFG-34HY1KXzhkY74bUMpoTbM3bsvEWRSkoCIZxW558VqGuG5Y94-llG7VwnyCIvsR3M1-9suLMQKauIBfLlCL947Hc14akTbIzTOOEcRul4JfSSaAav5lfYZt2UV9eJHvJ2AiCinz7_2jo7EhNY1nohP10uC0Pz0SWb5Dd5iwTx4_rtjkqe2uyA-fLcRPSO0pcSDD4a3Id3nloAk3vxwfp1RF5czw8RjFR_RFWo3EyB4e4tuF8C0oj9B-VbCgzuRbxfPdVvUs9CiLFv5kB3giAeM5tRRP1UEhblV_MvKE5oTOCYAq_K6gh4EdmTJ6Z7d48JZOPmC5-F73b0TegAgan-4jig1tOCtlJXV__xkSBlTBS3geqhoxGu3smMcSfvT7SK6LB8ADjhiKBMv4iKtepU5-2ROgpwa2H8-vr8WLEu0dBCjg1TY4kCbKxSeDy3NVeTX8Cc0gDgxTWAN_4hKpYV9xabnDpsYHeSMO49GwxWytuxZKQZSN4n2VGkZYndct-7oMlAoKrGP0BbL97IafSgZr1q5AZGCoT3s1M1R6U8vezpvYi_Lc7UyI0rbwojbFExgEdeTOuo7P2WnNEGnPGzFs8we_cDkXgD-Q4BUOwj7ixFkHk1FpFI52ga5a6XspLMAYR-7CzfmI4-ma6sXf7ubQcfAELcOzoz7xWAGAnAzScuVuMw0IdNhmANgvcRDxNO1JfcpZsiuNLJ9HRAxDSPKhUift3buIXqO_En8EkLFhZeR_QKYcKwjKTLkvWymEfaeU7jaewB-2_ngwpSNIgJQrx6BLCeRkeU5DfdFLpK7lh16UbgQlgQdSPL_r4NJOdp-pkaW7WNGMw72bg0iKlfO_Z3eO0_xKT7-etX5JuFVxYenAfZ55J5x1qJy2SYuzk8eJ3oWNvvHHwHgsadKJE1sKgHgePyeoWNw_1iYzhDJdoJtuf14XpS3CxphpjYFbxOdyFLyDD-4bJYSLj48rltCVOwGzprv6OrCfCt8Sr7qFBLwLFvTyZShHg_eZbapJnxLDLC1extz3rU9Pfjv9FTeW4BkKSvbGo-378Z_kI6ifK8k07T7sAgbNly_Uy2Dv1uX2BHT12hDBENHqWiabIJv1liSfmPv5-4elYoiNUTk66tkjboifERtQTB5olvPKlW--Ccr42Rhuy1mx3bQRyrUFNGRCK5txfeK9WClMaA11sImJdioM46ppQr5gvKxDjOSYL8Na57XnPZ6byucPVnMhkA3wb2xkO9SNGnt1nnj6KmyQeRPRcosScmL1r-6omb5DfZ5-f5sCqytD1UIqKoNDAjyMxCgjbPkG1As3YBj5huSHbHt7ceVrmpTvxwmrnzwWGbJZs1fBOtAKvExO3fDjuhm2GueVKy0dDSS-js8U2hi-uoaAdn1PpnDAdFD6QS3uIybfMF-l1N7g8NHN-DTLgt_-0bY8241XevxXnzxCRh2iupdX_LhPEKfZvzP2tXhz4M0MGJI27NVEvsSXiZUpy4xC3QEbkeAgqkyANN_y7nPYRRqjOh72FN7V2gSQEgpHdPzyFT6OpSutTevMaRfcaqlTJ6kbfiNGp4uD2zmYmTOKi4z3oCiZunZCE2J6QN_eYRurrrI5tMyj6E45zDzNNSO7A82SFLQIAmeDg1aUm4cu166iKZJChIxzcH5ushUgAp_w3KhiTj2e-ljMdUj884LPSg6cc7Cc0aXnDAJT2LFjcxZwqWr25Jdhni1P6T-rZw3DUlMvdeGolkzJc-dpMVXgtnrZjbD_5bZ3w9kASd_PtQE2RMUIhAzaO9Esqe5yrq5g8jUXItb2K-je1I5celZ901V7Y84BWXJ7RIW-fwhjASweKiG26iejH030nz28QwDpLeXdq42_kajPXhSEQmMV1pfI4gSYLVPBg1l9sN-3tNLP0gTYDJS5Xxa_CnppPOMKD_-Ea_8gNobc5gePNBtKOBorrDRFv1mbDpeKs6SRfeICGM5urma5XyTYOYkgGgJ7gRDi4RgixaQjAHQJuOE_Qoi9l12HCw9316mgl394UT5xakl3JnZR5LcxemWQaD07TK3I4t7cYPU7AU_rEzMy-QSaIKIsL9IHRGQ8iADljhYFbUOaXPj2SiorHpUYQFANgY4T76YnmfRosBuT8odb8FS2gyBTuixQHQnE3oLKZ8FeMsm1dMheV6KXycaCEYBMKny3vKbdcVfxILHPZEH9IFnYMfatL1BRrPZYCbX4HJIH8aLYuDfl_VupZ6y7mW4l6u0DmkGi_-9rDKPzC7UYNWN-szqW3oPtwhO6prqhVpBe5hRQoYeDiLogDAzcktKHdbwjgU4XRVRFqw9csKA1gN6DG6Y8K4WdGjwHZtoLrZQ1e4OorVFq7qZsxYo5xEenaVDBYbYAAzP-cY5oRJNdxK1t7fT_EjwqtPuK6PVSHlmMEkdxcR95lwxPqlXZoNQ2hAZelmj21yLU44Z64TPfQmsDG2CW1ymmrosSxaYc3ols387zHEL7Mav0NtnfKeiA9IFSceAcaviAi2RdJiUccY_nqTistIKC8ddx7WWqtrIKFFxVPjN5QPDlaV08oABLb4R0D_jBHyuTOeCw9xE9Tuxuw209VDH-JDy8A1HZCKRGrXZAbdraFPbJghxxKKLSLQFbqH6rytm9_DOKrTRCrmzu0UgPaLUEUK-d5CQjIoCNw5FdUO9-ZzhkARsgOVxTE16NoKSjw6mPIgqiHMIPHfaG8eaOii7DG4yjrcrUBu6fKqmbIIBftesNgIcax4dIw-yPLd4llCPdIVyi8D4Aall59X0K1Sp3gRt1HZV5cCdL7yj9RRx6rENDZ6AyoU_4NkqwUWhxHvGMgBvlpjv-kJ4jsF1pPbhTXKfh5GfxeNqlwrIe4UkpAskmOo5oLni59PKn8VifJGiYO4RWroyJQ; _ga_S07SYD5D4F=GS2.1.s1775027088$o2$g1$t1775028877$j60$l0$h0"
    )
    
    # Discovery URL
    url = "https://www.starlink.com/api/web-inventory/v2/service-lines"
    
    headers = {
        "accept": "application/json",
        "cookie": cookies_str,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print(f"[*] Calling ServiceLines API to find your REAL hardware IDs...")
    
    try:
        resp = httpx.get(url, headers=headers, timeout=10.0)
        
        print(f"[DEBUG] HTTP Status: {resp.status_code}")
        print(f"[DEBUG] Raw Response: {repr(resp.text)}")
        
        if resp.status_code == 200 and resp.text:
            data = resp.json()
            lines = data.get("serviceLines", [])
            print(f"\n[+] SUCCESS! Found {len(lines)} service lines:")
            for line in lines:
                print(f"  - Nickname:    {line.get('nickname', 'N/A')}")
                print(f"    硬件 ID (DEVICE ID): {line.get('starlinkId')}  <-- USE THIS!")
                print(f"    Account:      {line.get('accountNumber')}")
                print("-" * 40)
        else:
            print(f"[-] API Error: {resp.text}")
            
    except Exception as e:
        print(f"[-] Discovery failed: {e}")

if __name__ == "__main__":
    main()
