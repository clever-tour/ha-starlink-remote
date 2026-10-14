"""Cookie validation used by the config, options and re-authentication flows.

The flows used to accept any string containing an ``=`` as a credential and
reported success straight away. A stale or truncated cookie therefore still
ended in a "success" dialog - the entry was created, every account-API call
answered 401 and the data usage sensor sat at 0.0 until the coordinator raised
its own warning a minute later.

The flows now prove the cookie against the account API before they report
success, by replaying what the coordinator does when it starts up:

1. inject the pasted cookie string into a jar for ``.starlink.com``,
2. prime the session against the portal (this rotates the short-lived
   ``Starlink.Com.Access.*`` cookies, exactly like a browser tab would),
3. request the service-lines endpoint and require an authenticated answer that
   carries real service lines.

Only then is the cookie stored, so "success" means the account API already
answered with data - not that a string was written to disk.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from . import session
from .const import (
    STARLINK_AUTH_URL,
    STARLINK_WEB_SERVICE_LINES,
    UA,
)

_LOGGER = logging.getLogger(__name__)

#: Error keys the flows can show (see ``strings.json``).
ERROR_INVALID_AUTH = "invalid_auth"
ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_NO_SERVICE_LINES = "no_service_lines"

#: Bodies the account API returns when the cookie carries no live session.
#: ``token_expired`` is the answer to an aged copy of an otherwise valid cookie.
_AUTH_FAILURE_MARKERS = (
    "authenticated_user_required",
    "token_expired",
    "invalid_token",
)

#: The account API answers a bare request differently, so send what the portal
#: sends along with the cookie.
_API_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "origin": "https://www.starlink.com",
    "referer": "https://www.starlink.com/account/home",
}

#: The form is waiting for this answer, so keep the timeout short.
_TIMEOUT = 20.0


def _prime_session(client: httpx.Client) -> None:
    """Touch the portal endpoints so the session jar gets its rotated cookies.

    A failure here is not fatal: the service-lines request below is what decides
    whether the credential is usable.
    """
    headers = {
        "User-Agent": UA,
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    for url in ("https://www.starlink.com/account/home", STARLINK_AUTH_URL):
        try:
            client.get(url, headers=headers)
        except httpx.HTTPError as err:
            _LOGGER.debug("Cookie validation: priming %s failed: %s", url, err)


def _auth_error(response: httpx.Response) -> str | None:
    """Return an error key unless the response proves a live session.

    ``None`` means the cookie authenticated *and* the account API answered with
    service lines, i.e. the update the integration is about to poll will work.
    """
    if response.status_code in (401, 403):
        return ERROR_INVALID_AUTH
    if any(marker in response.text for marker in _AUTH_FAILURE_MARKERS):
        return ERROR_INVALID_AUTH
    if response.status_code != 200:
        return ERROR_CANNOT_CONNECT

    try:
        payload: Any = response.json()
    except ValueError:
        _LOGGER.debug("Cookie validation: service-lines answered non-JSON")
        return ERROR_INVALID_AUTH

    if not isinstance(payload, dict) or payload.get("isValid") is False:
        return ERROR_INVALID_AUTH

    content = payload.get("content")
    if not isinstance(content, dict):
        return ERROR_INVALID_AUTH
    if not content.get("results"):
        # Authenticated, but this account has nothing to poll - most often the
        # cookie belongs to a different account than the subscribed one.
        return ERROR_NO_SERVICE_LINES
    return None


def validate_cookie(cookie: str) -> str | None:
    """Return an error key when ``cookie`` is not a usable credential.

    SyncWorker: the flows call this through ``hass.async_add_executor_job``.
    """
    if not cookie:
        return ERROR_INVALID_AUTH

    try:
        with httpx.Client(http2=True, timeout=_TIMEOUT, follow_redirects=True) as client:
            session.apply_cookie(client, cookie)
            _prime_session(client)
            response = client.get(
                STARLINK_WEB_SERVICE_LINES,
                headers={
                    "User-Agent": UA,
                    "x-xsrf-token": session.xsrf_token(client, cookie),
                    **_API_HEADERS,
                },
            )
    except httpx.HTTPError as err:
        _LOGGER.debug("Cookie validation could not reach the account API: %s", err)
        return ERROR_CANNOT_CONNECT

    error = _auth_error(response)
    if error is None:
        _LOGGER.debug("Cookie validation accepted the new cookie (service-lines is live)")
    else:
        _LOGGER.debug(
            "Cookie validation rejected the new cookie: %s (HTTP %s)",
            error,
            response.status_code,
        )
    return error
