import json
import sys
from pathlib import Path
from unittest.mock import patch

# Add project root to sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from starlink_client.grpc_web_client import GrpcWebClient
from starlink_client.grpc_web_base_client import GrpcWebBaseClient

def main():
    # NEW API2 COOKIES
    cookies_str = (
        "_ga=GA1.1.953080577.1775024709; sx_selected_locale=en-US; "
        "__stripe_mid=b03f6830-cac5-40a4-a8c8-4bfcfe177ce7c50625; "
        "Starlink.Com.Sso.CheckSession=2F9F62A6293F6D05F6BF32CA51196E31; "
        "Starlink.Com.Sso=CfDJ8LtfW3omojlBhUQi_zkD2NShbWZu1o7RdYKGO53tv7d0aP2HnRrQvg797cNmHnzD9jV4SyHwUfURsi7W-_xYjAsjW_s-9ecxeAQOcSw6DEqEs5ZKysbTXnsh0r3NW7-wzS-BXGJwfF3zwAYoYm-_3_jzylou2sgbD35AJVSY7bNm5ZiwpMExbAAP_JOZtaAy71GuZR_GuTmnQlKbI--C3E_1R_bSMxO-I-E4Z37GrWcbuHnVfaKjLt0XP2NGDRSQ_NSlc08CaYTtR5WLLZJ3DgJgZ7Vp9Tj_6t6B8j9EHNw2xNhv5Dj-n5zHJeTEgr-ZijpWnpURih77FFjcfD4yQFk; "
        "starlink.com.account_number=ACC-5147187-41313-10; "
        "__stripe_sid=c55bb2f3-b616-4bdb-8f90-822b958d31abe29197; "
        "Starlink.Com.Access.V1=CfDJ8LtfW3omojlBhUQi_zkD2NRC9_XO117VckKXPtAC4vIbfVugrjZEZ68bIIV2wqTRwabhi6fwU_FvyJKc4Q-_JNrdU"
    )

    print("[*] Authenticating with API2 cookies...")
    
    with patch.object(GrpcWebBaseClient, "_refresh_auth", lambda x: None):
        try:
            client = GrpcWebClient(cookies_str, str(ROOT / ".api2_discovery_session"))
            
            print("[*] Calling get_service_lines...")
            lines = client.get_service_lines()
            
            if not lines:
                print("[!] No devices found.")
                return 0

            print(f"\n[+] SUCCESS! Found {len(lines)} device(s):")
            for line in lines:
                print(f"  - Nickname:    {getattr(line, 'nickname', 'N/A')}")
                print(f"    DEVICE ID:   {line.device_id}")
                print(f"    硬件 ID:      {getattr(line, 'hardware_id', 'N/A')}")
                print("-" * 40)
                
            return 0
        except Exception as exc:
            print(f"[-] Discovery failed: {exc}")
            return 1

if __name__ == "__main__":
    sys.exit(main())
