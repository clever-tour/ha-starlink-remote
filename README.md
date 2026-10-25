# Starlink Remote for Home Assistant

A Home Assistant custom integration for monitoring and controlling Starlink
hardware through the official SpaceX consumer cloud API. The integration requires
no local dish or router access: telemetry, account data and the restart command
are exchanged with `starlink.com` over HTTPS, authenticated with the session of a
signed-in browser.

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![HACS Action](https://github.com/clever-tour/ha-starlink-remote/actions/workflows/hacs.yml/badge.svg)](https://github.com/clever-tour/ha-starlink-remote/actions/workflows/hacs.yml)
[![Validate with hassfest](https://github.com/clever-tour/ha-starlink-remote/actions/workflows/hassfest.yml/badge.svg)](https://github.com/clever-tour/ha-starlink-remote/actions/workflows/hassfest.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Disclaimer**
> This project is not affiliated with, endorsed by, or supported by SpaceX or
> Starlink. It is an independent integration that uses the same cloud endpoints
> as the Starlink web application. Use it at your own risk.

## Contents

- [Features](#features)
- [Screenshots](#screenshots)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entities](#entities)
- [Account data](#account-data)
- [Session handling](#session-handling)
- [Diagnostics and privacy](#diagnostics-and-privacy)
- [Troubleshooting](#troubleshooting)
- [Support](#support)
- [Credits](#credits)
- [License](#license)

## Features

**Discovery and configuration**

- Automatic discovery of every dish and router on the account after a single
  sign-in cookie is supplied.
- Configuration, options and re-authentication are handled entirely through the
  Home Assistant user interface; no YAML is required.
- Several entries are supported, for several accounts or for the same account
  added twice, each with its own session, storage and entity identity.
- Every cookie is verified stage by stage (parsed, portal session primed,
  account API queried, service lines read, hardware discovered) and the dialog
  reports each step with its outcome and timing before anything is stored.

**Telemetry**

- State, uptime, throughput, latency, obstruction fraction, orientation, boot
  count, outage totals and searching events for the dish.
- Connectivity, uptime and Wi-Fi client counts, per band, for the router.
- **Power**: the dish's 15-minute average, or the router's Power-over-Ethernet
  draw when it supplies the dish.
- **Energy**: a cumulative kWh figure integrated from the dish's power series.
- **Data usage**: the current billing-cycle total, selected automatically from
  the available account sources.

**Events**

- Dish and router changes are published as typed events: restart, state
  transition, searching, obstruction, other outages, alerts, software-update
  transitions and Wi-Fi client changes.
- Each event carries a readable summary and its raw detail (cause, duration,
  alert name, before/after values). A **Last Event** sensor per device shows the
  most recent one without requiring a template.

**Operational behaviour**

- A session that SpaceX invalidated raises a fixable repair issue and a
  notification; the repair dialog accepts a fresh cookie and verifies that the
  integration comes back up before closing.
- Short-lived access cookies are refreshed automatically with a bearer token, so
  a valid session does not require the cookie to be pasted again.
- The integration is **read-only** except for the restart command. Stow, unstow
  and configuration writes are deliberately not implemented.

## Screenshots

| Dish sensors | Router sensors |
| :---: | :---: |
| <img src="docs/images/sensors-dish.png" alt="Sensors exposed for the Starlink dish" width="264"> | <img src="docs/images/sensors-router.png" alt="Sensors exposed for the Starlink router" width="265"> |

## Requirements

| Item | Requirement |
| --- | --- |
| Home Assistant | 2024.11 or newer |
| Account | An active Starlink consumer account (starlink.com, not the Enterprise portal) |
| Network | Outbound HTTPS access to `api.starlink.com` and `www.starlink.com` |
| Access | No local dish or router connectivity is required |

## Installation

### HACS (recommended)

1. Open **HACS** and select **Integrations**.
2. Open the menu in the top-right corner and choose **Custom repositories**.
3. Enter `https://github.com/clever-tour/ha-starlink-remote` and select the
   category **Integration**.
4. Add the repository, then install **Starlink Remote**.
5. Restart Home Assistant.

### Manual

1. Download the latest release.
2. Copy the `custom_components/starlink_remote` directory into the
   `custom_components` directory of your Home Assistant configuration.
3. Restart Home Assistant.

## Configuration

1. Navigate to **Settings → Devices & services**.
2. Select **Add integration** and search for **Starlink Remote**.
3. Paste the browser cookie of a signed-in Starlink session (see below).

One entry is created per account; the account number contained in the cookie is
recorded as the entry's unique identifier, and the entry title includes the last
eight digits so several accounts remain distinguishable.

While the cookie is being verified, the dialog reports the connection as it
progresses:

```text
### Starlink connection check

✅ Cookie parsed — 7 cookie pairs, account: 1234567 · 2 ms
✅ Portal primed — /account/home → HTTP 200, session cookies: 4 · 310 ms
✅ Account API answered — GET /api/webagg/v2/service-lines → HTTP 200, 1841 bytes · 180 ms
✅ Service lines — 1 service line(s), 1 terminal(s), 1 router(s) · 0 ms
✅ Hardware discovery — 2 device id(s): Router-A…, ut010203… · 0 ms

**Verdict:** session is live - the account API answered with data.
```

A refused cookie terminates on the same screen with the failing stage marked and
the verdict stated in full.

### Obtaining the cookie

1. Sign in at [starlink.com/account/home](https://www.starlink.com/account/home).
2. Open the browser developer tools (`F12`) and select the **Network** tab.
3. Reload the page.
4. Select any request to `www.starlink.com` and locate the `cookie` entry under
   **Request headers**.
5. Copy the complete value and paste it into the Home Assistant dialog.

> **Note**
> Signing in to starlink.com again invalidates the previously copied session. Use
> a dedicated browser profile when copying the cookie, or copy it immediately
> before configuring the integration.

> **Note**
> If the session is invalidated later, the integration does not need to be
> removed. Use the **Fix** button on the repair card, or the **Configure** option
> of the entry, to supply a fresh cookie. Entity history is preserved.

## Entities

| Entity | Device | Category |
| --- | --- | --- |
| State, Uptime, Downlink Throughput, Uplink Throughput, Ping Latency, Obstruction Fraction | Dish; State and Uptime also on the router | — |
| Boresight Azimuth, Tilt Angle, Boot Count, Searching Events, Total Outages | Dish | Diagnostic |
| WiFi Clients | Router | — |
| Power | Dish (15-minute average) and router (PoE, when it supplies the dish) | — |
| Energy | Dish (cumulative, from the power series) | Diagnostic |
| Data Usage (Total) | Dish (account-wide figure) | Diagnostic |
| Last Event | Dish and router | Diagnostic |
| Connected | Dish and router | — |
| Restart | Dish and router | — |
| Events | Dish and router | — |

Entities are attached to the dish and router devices discovered on the account,
so they can be assigned to an area like any other device.

### Events

The **Events** entity publishes every difference observed between two polls, and
each event carries a `summary` attribute in addition to its raw detail. The
**Last Event** sensor exposes the most recent event as its state.

| Event type | Meaning |
| --- | --- |
| `rebooted` | The boot counter increased, or uptime decreased. |
| `state_changed` | The connection or disablement state changed. |
| `searching` | A searching outage was recorded. |
| `obstructed` | An obstruction outage was recorded. |
| `outage` | Any other outage cause. |
| `alert` | A thermal, hardware or account alert became active. |
| `update_state_changed` | A software-update state transition occurred. |
| `clients_changed` | The number of Wi-Fi clients changed. |

## Account data

### Data usage

The **Data Usage (Total)** sensor reports the consumption of the current billing
cycle in gigabytes. The figure is selected automatically from the first source
that answers: the annotated billing-cycle aggregate, the account telemetry byte
counters, or the data-block export. Usage is summed across all service lines of
the account. The display is rounded to whole gigabytes; the exact value, the
cycle window, the plan bucket and the per-day series are available as attributes,
together with the source that produced the figure (`usage_source`).

### Power and energy

The **Power** sensor reports, in watts, either the dish's average over the last
15 minutes (computed from the per-second series in the dish history) or the
router's Power-over-Ethernet draw when the router supplies the dish. A device that
reports neither value receives no power entity.

The **Energy** sensor integrates the power series over time and exposes a
cumulative total in kilowatt-hours with `state_class: total_increasing`, which
allows Home Assistant to derive hourly, daily and monthly consumption. The total
is persisted across restarts and begins at zero when the series is first
observed.

### What the API reports

The connection state reflects the value returned by the API. The dish reports a
disablement code rather than a `CONNECTED`/`SEARCHING` enumeration; a code other
than `OKAY` (for example `BOOTING`, `STOWED` or `THERMAL_SHUTDOWN`) is reported
verbatim, and `CONNECTED` is reported otherwise. The router does not populate its
own state field, so its **State** reflects the device answering.

**Uptime** is presented in hours, with the raw value in seconds available as an
attribute. A duration device class is deliberately not declared: Home Assistant
converts durations into the unit system's unit, which would display seconds in a
metric configuration regardless of the declared unit.

## Session handling

The browser cookie contains short-lived access tokens and a longer-lived session.
When an access token is rejected, the integration obtains a bearer token from
`auth/auth/refresh-token` - the same call the web application uses - and retries
the request. The cookie stored in the entry remains the source of truth, so an
expired access token does not require the cookie to be pasted again.

## Diagnostics and privacy

Diagnostics can be downloaded from **Settings → Devices & services → Starlink
Remote → Download diagnostics**. The file contains the coordinator state, device
key names, session health and the resolved account figures, and redacts the
cookie, the account tail in the entry title, discovered hardware identifiers and
device identifiers. It is intended to be safe to attach to a public issue.

## Troubleshooting

**A repair card reports that the session expired.**
SpaceX invalidated the cookie, typically because the account was signed in again
elsewhere. Select **Fix** and paste a fresh cookie.

**Entities report `unknown` for a while.**
The account is polled at an interval (60 seconds by default). A first poll may
not have completed yet. A value that remains `unknown` indefinitely generally
indicates a metric that the current firmware does not report; see below.

**Data usage is unavailable or unexpectedly zero.**
The integration tries the account sources in order and records which one answered
in the `usage_source` attribute. If no source returns a value for the account, the
sensor remains `unknown` and the attribute is absent.

**Power is not available.**
Only hardware that reports PoE statistics or a power series exposes the sensor.
Bypassed routers and dishes without the series produce no power entity.

**Wi-Fi clients report zero.**
A router in bypass mode does not report clients; `wifi_bypassed` is set in the
attributes, which indicates a valid reading rather than a missing one.

**Diagnostics download.**
Add the following to `configuration.yaml` to capture a full poll cycle before
opening an issue:

```yaml
logger:
  logs:
    custom_components.starlink_remote: debug
```

## Support

- **Issues**: [github.com/clever-tour/ha-starlink-remote/issues](https://github.com/clever-tour/ha-starlink-remote/issues)
- **Community**: [Signal group](https://signal.group/#CjQKIGdi3Eu4cjebMN6Lmno_8BikvfyduehDNeBGTXjvHt7SEhD9VRQGqufkCsp8Khz7xKzT)

When reporting a problem, include the Home Assistant version, the integration
version, relevant log lines with debug logging enabled, and the diagnostics file.

## Credits

The generated protobuf modules under `custom_components/starlink_remote/spacex/`
originate from the [starlink-client](https://github.com/Eitol/starlink-client)
project by Hector Oliveros, whose examples and gRPC logic informed this
integration. That project is MIT licensed; its copyright and permission notice is
reproduced in [`custom_components/starlink_remote/spacex/LICENSE`](custom_components/starlink_remote/spacex/LICENSE).

## License

This integration is released under the [MIT License](LICENSE).
