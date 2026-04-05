# Starlink Remote for Home Assistant

A Homessistant integration for remote monitoring and control of Starlink hardware via the official SpaceX cloud consumer API.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![HACS Action](https://github.com/clever-tour/ha-starlink-remote/actions/workflows/hacs.yml/badge.svg)](https://github.com/clever-tour/ha-starlink-remote/actions/workflows/hacs.yml)
[![Validate with hassfest](https://github.com/clever-tour/ha-starlink-remote/actions/workflows/hassfest.yml/badge.svg)](https://github.com/clever-tour/ha-starlink-remote/actions/workflows/hassfest.yml)

**Topics:** `home-assistant`, `hacs`, `integration`, `starlink`, `remote-monitoring`

> [!IMPORTANT]
> This integration is provided "as-is". It has been primarily tested with the **Starlink Mini (v4)**. Compatibility with older circular or rectangular dishes is expected but not guaranteed.

## Features
- **Remote Access**: Monitor your dish from anywhere without needing to be on the local Starlink WiFi.
- **Auto-Discovery**: Automatically finds all Dishes and Routers associated with your account.
- **Metrics**: Real-time throughput (Up/Down), obstruction fraction, ping latency, orientation (azimuth/tilt), and uptime.
- **WiFi Insights**: Monitor connected client counts and hardware status.
- **Remote Control**: Support for **Reboot**, **Stow**, and **Unstow** commands directly from Home Assistant.
- **Robust Auth**: Handles session persistence and persistent cookie recovery.
<img width="264" height="693" alt="image" src="https://github.com/user-attachments/assets/8e9076da-c3b0-4f8e-8161-05a2d3fcfca3" />
<img width="265" height="268" alt="image" src="https://github.com/user-attachments/assets/e7f6ad29-4bd7-4018-bf43-f7f2b730d15f" />

## Installation

### Option 1: HACS (Recommended)
1. Open **HACS** in your Home Assistant instance.
2. Click the three dots in the top right and select **Custom repositories**.
3. Add `https://github.com/clever-tour/ha-starlink-remote` with category `Integration`.
4. Click **Install**.
5. Restart Home Assistant.

### Option 2: Manual
1. Download the latest release.
2. Copy the `custom_components/starlink_remote` folder to your HA `config/custom_components/` directory.
3. Restart Home Assistant.

## Configuration

1. Go to **Settings > Devices & Services**.
2. Click **Add Integration** and search for **Starlink Remote**.
3. Enter your Starlink browser cookie (see below).

### How to get your Login Cookie
This integration requires a browser session cookie to communicate with the Starlink cloud.
1. Log in to [starlink.com/account/home](https://www.starlink.com/account/home).
2. Open Browser Developer Tools (`F12`) and go to the **Network** tab.
3. Refresh the page.
4. Click on any request to `www.starlink.com` and find the `cookie:` header in the **Request Headers** section.
5. Copy the **entire string** and paste it into the Home Assistant configuration flow.

## Credits & Acknowledgments
Special thanks to **Eitol** for the excellent work on the [starlink-client](https://pypi.org/project/starlink-client/) library, which provided the foundational code examples and gRPC logic used to build this integration.

## Support
For help, bug reports, or feedback:
- **GitHub Issues**: [Open an issue](https://github.com/clever-tour/ha-starlink-remote/issues)
- **Signal Group**: [Join our community](https://signal.group/#CjQKIGdi3Eu4cjebMN6Lmno_8BikvfyduehDNeBGTXjvHt7SEhD9VRQGqufkCsp8Khz7xKzT)

---
*Created with gemini-cli.*
