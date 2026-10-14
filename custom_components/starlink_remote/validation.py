"""Cookie validation entry points shared by the flows.

The staged implementation lives in :mod:`flow_log`; this module owns the error
keys the flows hand to Home Assistant and a one-shot helper for callers that only
need the verdict.

An error key is a translation key first: every value below has a matching entry
in ``strings.json`` under ``config.error``, which is what the dialog renders.
"""
from __future__ import annotations

from .flow_log import CookieProbe

#: The account API refused the session (401/403, or a token error body).
ERROR_INVALID_AUTH = "invalid_auth"

#: Starlink could not be reached at all (DNS, TLS, timeout, 5xx).
ERROR_CANNOT_CONNECT = "cannot_connect"

#: The session works, but the account has nothing to poll.
ERROR_NO_SERVICE_LINES = "no_service_lines"


def validate_cookie(cookie: str) -> str | None:
    """Return an error key when ``cookie`` is not a usable credential.

    Runs the same phases the GUI shows, without keeping the log. Returns None
    when the account API answered with service lines.

    SyncWorker: the flows call this through ``hass.async_add_executor_job``.
    """
    probe = CookieProbe(cookie)
    try:
        while phase := probe.next_phase():
            probe.run_phase(phase)
    finally:
        probe.close()
    return probe.error
