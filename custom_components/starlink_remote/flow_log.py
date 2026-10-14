"""Staged cookie probe that powers the connection log in the GUI.

The cookie flows used to validate the credential in a single blocking call: the
dialog sat on a spinner and then answered with either a one-line error or a
"success" message. This module breaks that check into the individual steps the
integration actually performs, records what each one saw, and renders the whole
sequence as markdown. The flows show the log while the probe runs (one progress
step per phase) and again as a report before the flow finishes.

Two decisions worth knowing when reading the rendering code:

* The log is deliberately always English. Flow steps are translated by the
  frontend from ``strings.json``, but a *placeholders* value is a string the
  backend builds and Home Assistant renders verbatim, so there is no translation
  lookup available here. Technical detail is shown untranslated on purpose.
* The cookie value itself is never rendered. The log only ever carries derived
  facts: cookie pair counts, the account number, HTTP status codes, payload
  sizes and discovered hardware ids.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from . import session
from .const import STARLINK_AUTH_URL, STARLINK_WEB_SERVICE_LINES, UA

_LOGGER = logging.getLogger(__name__)

#: Phases of the probe, in order. ``reload`` is appended by the flows that run
#: inside an existing entry (options, re-authentication).
CONNECT_PHASES = ("parse", "portal", "account", "lines", "discover")

#: Human-readable phase names used in the log.
PHASE_LABELS = {
    "parse": "Cookie parsed",
    "portal": "Portal primed",
    "account": "Account API answered",
    "lines": "Service lines",
    "discover": "Hardware discovery",
    "reload": "Integration reloaded",
}

#: Bodies the account API returns when the cookie carries no live session.
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

_PORTAL_HEADERS = {
    "User-Agent": UA,
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

#: The dialog is waiting for the answer, so keep every call short.
_TIMEOUT = 20.0

#: Portal markup the coordinator also scrapes for hardware ids.
_ID_PATTERNS = (
    r"Router-[A-Fa-f0-9]{24}",
    r"ut[a-f0-9-]{36}",
    r"selectedDevice=([A-Fa-f0-9-]+)",
)


@dataclass(slots=True)
class PhaseResult:
    """What one probe phase saw, ready to be rendered in the log."""

    key: str
    ok: bool
    detail: str
    ms: int
    #: ``True`` when the phase did not do what was expected but is not fatal
    #: (for example the portal did not rotate its session cookies).
    warning: bool = False

    @property
    def mark(self) -> str:
        """Return the symbol shown in front of the phase in the log."""
        if not self.ok:
            return "❌"
        return "⚠️" if self.warning else "✅"


class CookieProbe:
    """Run the connection phases of a cookie and keep a record of each one.

    SyncWorker: every phase makes blocking HTTP calls, so the flows run
    :meth:`run_phase` through ``hass.async_add_executor_job``.
    """

    def __init__(self, cookie: str, extra_phases: tuple[str, ...] = ()) -> None:
        self.cookie = cookie
        self.phases: tuple[str, ...] = CONNECT_PHASES + extra_phases
        self.results: list[PhaseResult] = []
        #: Error key (see ``strings.json``) that stops the flow, if any.
        self.error: str | None = None
        self.account: str | None = None
        #: Short description of what discovery found, used by the coordinator-less
        #: flows to say something concrete about the account.
        self.hardware: list[str] = []
        self._client = httpx.Client(
            http2=True, timeout=_TIMEOUT, follow_redirects=True
        )
        self._service_lines: Any = None
        self._portal_html = ""

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Release the HTTP client held for the duration of the probe."""
        try:
            self._client.close()
        except Exception:  # pragma: no cover - defensive, closing must not fail a flow
            _LOGGER.debug("Cookie probe: closing the HTTP client failed", exc_info=True)

    def next_phase(self) -> str | None:
        """Return the next phase to run, or ``None`` when all of them ran."""
        done = {result.key for result in self.results}
        for phase in self.phases:
            if phase not in done:
                return phase
        return None

    def add_result(self, result: PhaseResult) -> None:
        """Record a phase the flow itself ran (used for ``reload``)."""
        self.results.append(result)
        _LOGGER.info(
            "Cookie check step %s: %s (%s)", result.key, result.detail, result.mark
        )

    def phase_result(self, name: str) -> PhaseResult | None:
        """Result of a phase that already ran, if any."""
        for result in self.results:
            if result.key == name:
                return result
        return None

    # -- phases ------------------------------------------------------------

    def run_phase(self, name: str) -> None:
        """Run one phase and record its result.

        SyncWorker: called in an executor thread by the flows.
        """
        if self.phase_result(name) is not None:
            # A second configure request raced the running phase: never log a
            # phase twice, the result of the first run stands.
            return
        started = time.perf_counter()
        try:
            self.add_result(getattr(self, f"_phase_{name}")())
        except httpx.HTTPError as err:
            _LOGGER.debug("Cookie check: phase %s could not reach Starlink: %s", name, err)
            self.error = "cannot_connect"
            self.add_result(
                PhaseResult(name, False, f"network error: {type(err).__name__}", _ms(started))
            )
        except Exception as err:  # noqa: BLE001 - a probe must never break the flow
            _LOGGER.debug("Cookie check: phase %s failed unexpectedly: %s", name, err, exc_info=True)
            self.error = self.error or "cannot_connect"
            self.add_result(
                PhaseResult(name, False, f"unexpected error: {type(err).__name__}", _ms(started))
            )

    def _phase_parse(self) -> PhaseResult:
        """Inject the pasted string into a jar and report what it carried."""
        started = time.perf_counter()
        pairs = [part for part in self.cookie.split(";") if "=" in part]
        access = re.findall(r"Starlink\.Com\.Access\.[^=;]+=", self.cookie)
        self.account = session.account_number_from_cookie(self.cookie)
        xsrf = bool(session.xsrf_token(self._client, self.cookie))
        session.apply_cookie(self._client, self.cookie)

        detail = (
            f"{len(pairs)} cookie pairs, {len(access)} `Starlink.Com.Access.*`, "
            f"XSRF token: {'present' if xsrf else 'absent'}, "
            f"account: {self.account or 'not found in cookie'}"
        )
        # A cookie without an account number can still authenticate, but the
        # flow cannot use it as a unique id, and it usually means a partial copy.
        return PhaseResult(
            "parse",
            True,
            detail,
            _ms(started),
            warning=self.account is None,
        )

    def _phase_portal(self) -> PhaseResult:
        """Touch the portal so the jar gets its rotated session cookies."""
        started = time.perf_counter()
        statuses = []
        for url in ("https://www.starlink.com/account/home", STARLINK_AUTH_URL):
            response = self._client.get(url, headers=_PORTAL_HEADERS)
            statuses.append(f"{urlparse(url).path} → HTTP {response.status_code}")
            if url.endswith("/account/home") and response.status_code == 200:
                self._portal_html = response.text

        rotated = len(
            [c for c in self._client.cookies.jar if c.name.startswith("Starlink.Com.Access")]
        )
        return PhaseResult(
            "portal",
            True,
            f"{', '.join(statuses)}, session cookies: {rotated}",
            _ms(started),
            warning=rotated == 0,
        )

    def _phase_account(self) -> PhaseResult:
        """Ask the account API for the service lines and judge the answer."""
        started = time.perf_counter()
        response = self._client.get(
            STARLINK_WEB_SERVICE_LINES,
            headers={
                "User-Agent": UA,
                "x-xsrf-token": session.xsrf_token(self._client, self.cookie),
                **_API_HEADERS,
            },
        )
        detail = (
            f"GET /api/webagg/v2/service-lines → HTTP {response.status_code}, "
            f"{len(response.content)} bytes"
        )

        if response.status_code in (401, 403) or any(
            marker in response.text for marker in _AUTH_FAILURE_MARKERS
        ):
            self.error = "invalid_auth"
            return PhaseResult("account", False, f"{detail} (session refused)", _ms(started))
        if response.status_code != 200:
            self.error = "cannot_connect"
            return PhaseResult("account", False, detail, _ms(started))

        try:
            self._service_lines = response.json()
        except ValueError:
            self.error = "invalid_auth"
            return PhaseResult("account", False, f"{detail} (non-JSON body)", _ms(started))

        payload = self._service_lines
        if not isinstance(payload, dict) or payload.get("isValid") is False:
            self.error = "invalid_auth"
            return PhaseResult("account", False, f"{detail} (marked invalid)", _ms(started))

        return PhaseResult("account", True, detail, _ms(started))

    def _phase_lines(self) -> PhaseResult:
        """Summarise the service lines the account answered with."""
        started = time.perf_counter()
        results = _results_of(self._service_lines)
        if not results:
            # Authenticated, but this account has nothing to poll - most often
            # the cookie belongs to a different account than the subscribed one.
            self.error = "no_service_lines"
            return PhaseResult("lines", False, "the account reported no service lines", _ms(started))

        terminals = 0
        routers = 0
        for result in results:
            for terminal in result.get("userTerminals") or []:
                terminals += 1
                routers += len(terminal.get("routers") or [])

        detail = (
            f"{len(results)} service line(s), {terminals} terminal(s), "
            f"{routers} router(s)"
        )
        return PhaseResult("lines", True, detail, _ms(started), warning=not terminals)

    def _phase_discover(self) -> PhaseResult:
        """Look for hardware ids, the way the coordinator discovers them."""
        started = time.perf_counter()
        self.hardware = []
        for result in _results_of(self._service_lines):
            for terminal in result.get("userTerminals") or []:
                if terminal_id := terminal.get("userTerminalId"):
                    self.hardware.append(str(terminal_id))
                for router in terminal.get("routers") or []:
                    if router_id := router.get("routerId"):
                        self.hardware.append(str(router_id))

        if self._portal_html:
            found: set[str] = set()
            for pattern in _ID_PATTERNS:
                found.update(re.findall(pattern, self._portal_html))
            self.hardware.extend(sorted(found))

        self.hardware = sorted(set(self.hardware))
        if not self.hardware:
            # The coordinator survives this (it polls ids it already knows), but
            # it means the account page did not mention a dish or a router.
            return PhaseResult(
                "discover",
                True,
                "no hardware id found (the account page may be a different view)",
                _ms(started),
                warning=True,
            )

        preview = ", ".join(_shorten(item) for item in self.hardware[:4])
        more = f" (+{len(self.hardware) - 4} more)" if len(self.hardware) > 4 else ""
        return PhaseResult(
            "discover", True, f"{len(self.hardware)} device id(s): {preview}{more}", _ms(started)
        )

    # -- rendering ---------------------------------------------------------

    def verdict(self) -> str:
        """Return the closing line of the log."""
        if self.error == "invalid_auth":
            return "**Verdict:** the account API refused this session - the cookie is stale or was copied incompletely."
        if self.error == "no_service_lines":
            return "**Verdict:** the cookie works, but this account has no Starlink service to poll."
        if self.error == "cannot_connect":
            return "**Verdict:** Starlink could not be reached from this Home Assistant instance."
        if self.error:
            return f"**Verdict:** {self.error}."
        return "**Verdict:** session is live - the account API answered with data."

    def render(self, *, title: str, footer: str | None = None) -> str:
        """Render the phases as markdown for a flow description placeholder."""
        lines = [f"### {title}", ""]
        if not self.results:
            lines.append("_Starting…_")
        for result in self.results:
            label = PHASE_LABELS.get(result.key, result.key)
            lines.append(f"{result.mark} **{label}** — {result.detail} · `{result.ms} ms`")
        # A check that stopped early has no phases left to run either, so the
        # verdict is shown whenever there is an error or the sequence finished.
        if self.error or (self.results and not self.next_phase()):
            lines.extend(["", self.verdict()])
        if footer:
            lines.extend(["", footer])
        return "\n".join(lines)


def _results_of(payload: Any) -> list[dict[str, Any]]:
    """Return the service-line entries of an account API payload."""
    if not isinstance(payload, dict):
        return []
    results = payload.get("content", {}).get("results") if isinstance(payload.get("content"), dict) else None
    return [item for item in results or [] if isinstance(item, dict)]


def _shorten(value: str, keep: int = 8) -> str:
    """Shorten a long hardware id for the log."""
    return value if len(value) <= keep + 4 else f"{value[:keep]}…"


def _ms(started: float) -> int:
    """Return the elapsed milliseconds since ``started``."""
    return int((time.perf_counter() - started) * 1000)


__all__ = [
    "CONNECT_PHASES",
    "CookieProbe",
    "PHASE_LABELS",
    "PhaseResult",
]
