# Starlink Remote for Home Assistant

This Home Assistant integration allows for remote monitoring of Starlink hardware via the cloud API. It was created using **gemini-cli** with the **gemini-3-pro** model.

> [!IMPORTANT]
> This integration is provided "as-is" without any claims on quality or reliability. It has only been tested with the **Starlink Mini (v4)**. Compatibility with other models is unknown.

## Features
- **Auto-Discovery**: Finds your Starlink Dish and Router automatically via your account.
- **Hardware Grouping**: Entities are grouped under their respective hardware devices.
- **Remote Access**: No local network connection to the dish is required.
- **Metrics**: Throughput, obstruction data, orientation, uptime, and WiFi client counts.

## How to use
1. Copy the `starlink_remote` folder to your `custom_components/` directory.
2. Restart Home Assistant.
3. Add the integration through the UI (**Settings > Devices & Services**).

## Getting your Login Cookie
This integration requires a browser cookie to authenticate with the Starlink cloud.
1. Log in to [starlink.com/account/home](https://www.starlink.com/account/home).
2. Open Browser Developer Tools (F12) and go to the **Network** tab.
3. Refresh the page.
4. Click on any request to `www.starlink.com` and find the `cookie:` field in the **Request Headers**.
5. Copy the entire string and paste it into the integration configuration.

## Technical Notes
- **Polling**: The integration polls data via a gRPC-Web tunnel to the Starlink management API.
- **Session Persistence**: It performs a session "priming" cycle on every update to keep the connection alive.
- **XSRF**: It automatically handles XSRF token synchronization between subdomains.

---
*Created with gemini-cli and gemini-3-pro.*
