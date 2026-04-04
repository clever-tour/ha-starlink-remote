import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

# Add project root to sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from starlink_client.grpc_web_client import GrpcWebClient
from starlink_client.grpc_web_base_client import GrpcWebBaseClient

def main():
    cookies_str = os.environ.get("STARLINK_COOKIE")
    if not cookies_str:
        print("[-] Error: STARLINK_COOKIE environment variable not set")
        return 1
    
    # Extract account number if present to help with debugging
    account_number = "Unknown"
    for part in cookies_str.split(";"):
        if "starlink.com.account_number=" in part:
            account_number = part.split("=")[1]
            break

    print(f"[*] Authenticating for account {account_number}...")
    
    with patch.object(GrpcWebBaseClient, "_refresh_auth", lambda x: None):
        try:
            client = GrpcWebClient(cookies_str, str(ROOT / ".list_devices_session"))
            
            print("[*] Fetching service lines...")
            lines = client.get_service_lines()
            
            if not lines:
                print("[!] No service lines found for this account.")
                return 0

            print(f"\n[+] Found {len(lines)} service lines:")
            for line in lines:
                print(f"  - Nickname: {getattr(line, 'nickname', 'N/A')}")
                print(f"    Device ID: {line.device_id}")
                print(f"    Hardware ID: {getattr(line, 'hardware_id', 'N/A')}")
                print("-" * 30)
                
            return 0
        except Exception as exc:
            import traceback
            print(f"[-] Failed to list devices:")
            traceback.print_exc()
            return 1

if __name__ == "__main__":
    sys.exit(main())
