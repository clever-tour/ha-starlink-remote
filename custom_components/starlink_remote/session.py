"""Browser-session helpers shared by the coordinator and the config flows.

The integration authenticates with the cookie string a user pasted from the
browser. That string is injected into an httpx cookie jar, primed against the
portal - which rotates the short-lived ``Starlink.Com.Access.*`` cookies - and
then reused for the account-API and telemetry calls. Keeping the parsing here
means the flows validate exactly the session the coordinator is about to build.
"""
from __future__ import annotations

import re

import httpx

#: Cookie pair that carries the account number of the signed-in subscription.
ACCOUNT_NUMBER_COOKIE = "starlink.com.account_number"

#: The portal issues its cookies for the whole starlink.com domain.
COOKIE_DOMAIN = ".starlink.com"

#: Cookie the portal mirrors into the ``x-xsrf-token`` header.
XSRF_COOKIE = "XSRF-TOKEN"


def apply_cookie(client: httpx.Client, raw_cookie: str) -> None:
    """Inject a raw browser cookie string into the client's jar."""
    if not raw_cookie:
        return
    for part in raw_cookie.split(";"):
        if "=" in part:
            key, value = part.strip().split("=", 1)
            client.cookies.set(key, value, domain=COOKIE_DOMAIN)


def account_number_from_cookie(raw_cookie: str) -> str | None:
    """Return the Starlink account number carried by a raw cookie string.

    Used as the config flow's unique id: the account number identifies the
    subscription, so two attempts for the same account are recognised as a
    duplicate entry instead of a second integration.
    """
    for part in raw_cookie.split(";"):
        name, _, value = part.strip().partition("=")
        if name == ACCOUNT_NUMBER_COOKIE and value:
            return value
    return None


def xsrf_token(client: httpx.Client, raw_cookie: str) -> str:
    """Return the XSRF token from the jar, or from the raw string when absent."""
    token = client.cookies.get(XSRF_COOKIE, domain=COOKIE_DOMAIN, default="")
    if token:
        return token
    match = re.search(rf"{XSRF_COOKIE}=([^;]+)", raw_cookie)
    if match is None:
        return ""
    return match.group(1) or ""
