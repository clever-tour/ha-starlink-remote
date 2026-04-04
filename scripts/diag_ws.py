import asyncio
import json
import websockets
import sys

async def diagnose(url, token):
    uri = f"{url.replace('http', 'ws')}/api/websocket"
    async with websockets.connect(uri) as ws:
        # Auth
        await ws.recv() # auth_required
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        await ws.recv() # auth_ok
        
        # Try to get supported features or just test a few commands
        commands = [
            "config/config_entries/get_entries",
            "config/area_registry/list",
        ]
        
        for i, cmd in enumerate(commands, 1):
            msg = {"id": i, "type": cmd}
            if "flow" in cmd:
                msg["handler"] = "starlink_ha"
            await ws.send(json.dumps(msg))
            resp = json.loads(await ws.recv())
            print(f"Command '{cmd}': {resp.get('error', {}).get('code', 'SUCCESS')}")
            if resp.get('success'):
                print(f"  Result: {resp.get('result')}")

if __name__ == "__main__":
    url = "http://192.168.3.26:8123"
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIzNTA4MGMyZjNmMDQ0NmEzYWYxN2NhMmQ5ODEyNTY3YiIsImlhdCI6MTc3NTA0MjM4MSwiZXhwIjoyMDkwNDAyMzgxfQ.OufTnfuX_Fn22d7V3ffaVoc35DKl7zTvbi1pIw2vbzI"
    asyncio.run(diagnose(url, token))
