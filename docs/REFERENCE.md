# Reference: entities, events, account data and sessions


Detailed reference for the entities, event types and account figures exposed by
the Starlink Remote integration. The [README](../README.md) covers installation,
configuration and troubleshooting.


## Screenshots


| Dish sensors | Router sensors |
| :---: | :---: |
| <img src="images/sensors-dish.png" alt="Sensors exposed for the Starlink dish" width="264"> | <img src="images/sensors-router.png" alt="Sensors exposed for the Starlink router" width="265"> |

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
