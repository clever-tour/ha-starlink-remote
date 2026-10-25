"""Config, options and re-authentication flow for Starlink Remote.

Every flow that takes a cookie (initial setup, "Configure" and the repair fix)
runs the same connection to Starlink and shows what it is doing while it does
it. ``flow_log.CookieProbe`` does the work phase by phase; the mix-in below turns
those phases into GUI progress steps, so the dialog lists each step as it
completes instead of sitting on an unexplained spinner, and finishes with the
full log on a confirmation step.

A cookie is only ever stored after the account API has answered with real
service lines - and, when the flow runs inside an existing entry, after that
entry has come back up and polled successfully. "Success" therefore means the
integration is already reading live data, not that a string was written to disk.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowHandler, FlowResult
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import storage
from .const import CONF_COOKIE, DEFAULT_TITLE, DOMAIN
from .flow_log import CookieProbe, PhaseResult
from .session import account_number_from_cookie
from .validation import ERROR_CANNOT_CONNECT, ERROR_INVALID_AUTH

_LOGGER = logging.getLogger(__name__)

#: The cookie is a credential: the selector masks it while typing, so it never
#: sits in plain sight in the browser window (or in a screenshot of it).
_COOKIE_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

#: Setup and re-authentication: a cookie has to be typed to continue.
COOKIE_SCHEMA = vol.Schema({vol.Required(CONF_COOKIE): _COOKIE_SELECTOR})

#: Options: an empty field means "keep the stored cookie", which is why the
#: stored value is not prefilled into the form.
OPTIONS_SCHEMA = vol.Schema({vol.Optional(CONF_COOKIE, default=""): _COOKIE_SELECTOR})

#: Steps that only report: the log is in the description, submitting closes them.
CONFIRM_SCHEMA = vol.Schema({})

#: Guide shown under the cookie box, kept in one place for all three flows.
_COOKIE_HELP = (
    "Copy the value of the `cookie` request header from a logged-in "
    "starlink.com tab (F12 → Network → any request to www.starlink.com). "
    "The connection is tested step by step and nothing is stored unless the "
    "account API answers with your service lines."
)


def looks_like_cookie(raw: str) -> bool:
    """Return True when the input can be a browser cookie string.

    A deliberate cheap check, run before the credential is sent anywhere: it
    only catches the obvious mistakes (an empty field, a pasted URL).
    """
    return "=" in raw and not raw.startswith("http")


def _update_is_live(hass: HomeAssistant, entry_id: str) -> bool:
    """Return True when the entry is running and its first poll succeeded.

    A reload awaits the coordinator's first refresh, so after
    ``async_reload()`` this reflects the data update with the new cookie: a
    session that only *looks* valid fails here.
    """
    coordinator = hass.data.get(DOMAIN, {}).get(entry_id)
    return coordinator is not None and coordinator.last_update_success


class CookieConnectFlow(FlowHandler):
    """Mix-in: run a :class:`CookieProbe` as a sequence of progress steps.

    The flow manager re-invokes ``async_step_connect`` every time the progress
    task it was handed finishes, which is what makes the log grow in the dialog
    instead of appearing all at once at the end.
    """

    _probe: CookieProbe | None = None
    _connect_cookie: str = ""
    _connect_title: str = ""
    _connect_log_title: str = ""
    #: Step that asks for the cookie; the failure path renders it again.
    _connect_entry_step: str = "user"
    _cookie_schema: vol.Schema = COOKIE_SCHEMA
    #: Progress task of the phase that is currently running (re-entry guard).
    _phase_task: asyncio.Task | None = None
    _phase_task_phase: str = ""
    #: Phases already handed to a task, so one can never run twice.
    _started_phases: set[str] = frozenset()  # type: ignore[assignment]
    #: Result handed over once every phase is done; a later configure request
    #: must see this again instead of starting the probe over.
    _connect_done_result: FlowResult | None = None

    # -- the cookie form ---------------------------------------------------

    def _async_cookie_form(
        self,
        *,
        step_id: str | None = None,
        errors: dict[str, str] | None = None,
    ) -> FlowResult:
        """Show the cookie form, with the log of a previous attempt when there is one.

        ``step_id`` defaults to the step that asked for the cookie, so the
        translation the frontend renders always matches the step the user is
        on - the failure path re-renders the same form.
        """
        return self.async_show_form(
            step_id=step_id or self._connect_entry_step,
            data_schema=self._cookie_schema,
            errors=errors,
            description_placeholders={"guide": _COOKIE_HELP, "log": self._log()},
        )

    # -- probe driving -----------------------------------------------------

    def _async_start_connect(
        self,
        cookie: str,
        *,
        entry_step: str | None = None,
        progress_title: str,
        log_title: str,
    ) -> FlowResult:
        """Start the probe and show the first progress step."""
        if entry_step is not None:
            self._connect_entry_step = entry_step
        self._probe = CookieProbe(cookie, extra_phases=self._extra_phases())
        self._phase_task = None
        self._phase_task_phase = ""
        self._started_phases = set()
        self._connect_done_result = None
        self._connect_cookie = cookie
        self._connect_title = progress_title
        self._connect_log_title = log_title
        return self._async_advance_connect()

    def _extra_phases(self) -> tuple[str, ...]:
        """Return phases the concrete flow adds after the cookie itself."""
        return ()

    def _async_advance_connect(self) -> FlowResult:
        """Run the next phase, or finish the sequence when none is left.

        Re-entrant on purpose: Home Assistant calls this again every time the
        progress task it was handed finishes. A configure request that arrives
        while a phase is still running must not start that phase twice, so the
        running task is remembered and re-shown instead.
        """
        probe = self._probe
        if probe is None:  # pragma: no cover - defensive, cannot happen
            # Nothing to drive the phases with: show the cookie form again
            # rather than leaving the dialog on an empty progress step.
            return self._async_cookie_form()

        if self._connect_done_result is not None:
            return self._connect_done_result

        if (
            self._phase_task is not None
            and not self._phase_task.done()
            and probe.phase_result(self._phase_task_phase) is None
        ):
            return self.async_show_progress(
                step_id="connect",
                progress_action=self._phase_task_phase,
                description_placeholders={"log": probe.render(title=self._connect_title)},
                progress_task=self._phase_task,
            )

        if (phase := probe.next_phase()) is not None:
            if phase in self._started_phases:
                # The phase was handed out but never reported an outcome; record
                # it and move on, never start the same phase twice or the
                # progress step would be re-entered for ever.
                probe.add_result(
                    PhaseResult(phase, False, "the phase did not report a result", 0)
                )
                return self._async_advance_connect()
            self._started_phases.add(phase)
            self._phase_task_phase = phase
            self._phase_task = self.hass.async_create_task(self._async_run_phase(phase))
            self.async_update_progress(len(probe.results) / len(probe.phases))
            return self.async_show_progress(
                step_id="connect",
                progress_action=phase,
                description_placeholders={
                    "log": probe.render(title=self._connect_title)
                },
                progress_task=self._phase_task,
            )

        return self._async_connect_done()

    async def _async_run_phase(self, phase: str) -> None:
        """Run one phase, always recording an outcome.

        A phase that raises before it records a result would be handed to Home
        Assistant again on every re-entry, which spins the flow forever, so any
        failure is recorded here as well.
        """
        probe = self._probe
        assert probe is not None
        started = time.perf_counter()
        try:
            if phase == "reload":
                await self._async_phase_reload()
                return
            await self.hass.async_add_executor_job(probe.run_phase, phase)
        except Exception as err:
            _LOGGER.debug("Cookie check: phase %s failed: %s", phase, err, exc_info=True)
            if probe.phase_result(phase) is None:
                probe.error = probe.error or ERROR_CANNOT_CONNECT
                probe.add_result(
                    PhaseResult(
                        phase,
                        False,
                        f"the phase failed: {type(err).__name__}",
                        round((time.perf_counter() - started) * 1000),
                    )
                )

    async def _async_phase_reload(self) -> None:
        """Phase used by the flows that run inside an existing entry."""
        raise NotImplementedError

    async def async_step_connect(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Progress step: entered again by Home Assistant after every phase."""
        return self._async_advance_connect()

    def _async_connect_done(self) -> FlowResult:
        """All phases ran: either report the failure or move on to the report."""
        probe = self._probe
        assert probe is not None
        probe.close()
        self._phase_task = None
        self._phase_task_phase = ""

        if probe.error:
            _LOGGER.info("Cookie check failed: %s", probe.error)
            result = self.async_show_progress_done(next_step_id="failed")
        else:
            result = self.async_show_progress_done(next_step_id="confirm")
        self._connect_done_result = result
        return result

    async def async_step_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the log of a failed check and offer the cookie form again."""
        probe = self._probe
        return self._async_cookie_form(
            errors={
                "base": probe.error if probe and probe.error else ERROR_CANNOT_CONNECT
            }
        )

    def _log(self, *, footer: str | None = None) -> str:
        """Render the probe log for the current step."""
        probe = self._probe
        if probe is None:  # pragma: no cover - defensive
            return ""
        return probe.render(title=self._connect_log_title, footer=footer)


class StarlinkConfigFlow(CookieConnectFlow, config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration and re-authentication."""

    #: Version 2 added the account number as the entry unique id; version 3
    #: moved the stored session files and the entity/device identity of every
    #: entry under its own entry id, so several entries can coexist. Entries
    #: created before that are migrated in async_migrate_entry().
    VERSION = 3

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle initial configuration."""
        self._connect_entry_step = "user"
        if user_input is not None:
            cookie = user_input[CONF_COOKIE].strip()
            if not looks_like_cookie(cookie):
                return self._async_cookie_form(errors={"base": ERROR_INVALID_AUTH})
            return self._async_start_connect(
                cookie,
                entry_step="user",
                progress_title="Testing the new cookie",
                log_title="Starlink connection check",
            )

        return self._async_cookie_form()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the connection log and create the entry when it is submitted."""
        if user_input is None:
            return self.async_show_form(
                step_id="confirm",
                data_schema=CONFIRM_SCHEMA,
                description_placeholders={
                    "log": self._log(
                        footer="Submit to add the integration. Entities appear once "
                        "the first poll has run."
                    )
                },
            )

        cookie = self._connect_cookie

        # The integration may be added more than once - several accounts, or
        # the same account twice - so the account number is still recorded as
        # the unique id but no longer blocks a second entry. The title carries
        # the account tail, because that is what the user sees in the entry
        # list, in the repair issue and in the session-expired notification.
        account = account_number_from_cookie(cookie)
        if account:
            # A second entry for the same account is allowed on purpose, so the
            # unique id has to be unique per entry: Home Assistant removes an
            # existing entry when a new flow finishes with the same unique id,
            # which would silently replace the first account instead of adding
            # a second one.
            unique_id = account
            taken = {
                existing.unique_id
                for existing in self.hass.config_entries.async_entries(DOMAIN)
            }
            index = 2
            while unique_id in taken:
                unique_id = f"{account}#{index}"
                index += 1
            if unique_id != account:
                _LOGGER.info(
                    "Adding another entry for the Starlink account ending in %s",
                    account[-8:],
                )
            await self.async_set_unique_id(unique_id)

        return self.async_create_entry(
            title=entry_title(self.hass, account), data={CONF_COOKIE: cookie}
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle re-authentication when the cookie expired.

        Home Assistant seeds a re-authentication flow with the data of the
        entry - the cookie that has just expired. That value arrives here as
        ``user_input`` even though the user typed nothing, so it must not be
        taken for a submitted cookie: doing so ran the whole connection check
        on the dead credential before the dialog had even been shown, and
        opened the repair with a failed log instead of the form.
        """
        return await self.async_step_reauth_confirm(None)

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask for a fresh cookie and test it with the connection log."""
        # Keep the form's step id (and the failed-attempt form) on this step.
        self._connect_entry_step = "reauth_confirm"
        if user_input is not None:
            cookie = user_input[CONF_COOKIE].strip()
            if not looks_like_cookie(cookie):
                return self._async_cookie_form(errors={"base": ERROR_INVALID_AUTH})
            return self._async_start_connect(
                cookie,
                entry_step="reauth_confirm",
                progress_title="Testing the new cookie",
                log_title="Starlink connection check",
            )

        return self._async_cookie_form()

    def _extra_phases(self) -> tuple[str, ...]:
        """Re-authentication also proves that the entry comes back up."""
        if self._connect_entry_step == "user":
            # Setting up a brand new entry: there is no entry to reload yet,
            # and reloading one here would loop without ever recording a result.
            return ()
        return ("reload",)

    async def _async_phase_reload(self) -> None:
        """Store the cookie, reload the entry and check the first poll."""
        probe = self._probe
        assert probe is not None
        await async_store_and_reload(
            self.hass, self._get_reauth_entry(), self._connect_cookie, probe
        )
        self.async_update_progress(len(probe.results) / len(probe.phases))

    def _async_connect_done(self) -> FlowResult:
        """Finish on the re-authentication step, not on the setup confirmation."""
        probe = self._probe
        assert probe is not None
        if self._connect_entry_step == "user":
            return super()._async_connect_done()
        probe.close()
        if probe.error:
            _LOGGER.info("Re-authentication check failed: %s", probe.error)
            result = self.async_show_progress_done(next_step_id="failed")
        else:
            result = self.async_show_progress_done(next_step_id="reauth_done")
        self._connect_done_result = result
        return result

    async def async_step_reauth_done(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Close a successful re-authentication."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_done",
                data_schema=CONFIRM_SCHEMA,
                description_placeholders={
                    "log": self._log(
                        footer="Submit to close the repair and keep the new session."
                    )
                },
            )
        return self.async_abort(reason="reauth_successful")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow for this handler.

        The handler takes no arguments: Home Assistant passes ``config_entry``
        to the options flow itself and ``OptionsFlow.config_entry`` is a
        read-only property, so assigning to it raises an AttributeError.
        """
        return StarlinkOptionsFlowHandler()


class StarlinkOptionsFlowHandler(CookieConnectFlow, config_entries.OptionsFlow):
    """Handle the options flow: replacing an expired cookie.

    Home Assistant enters an options flow on the ``user`` step (cores from
    2026.x on; earlier cores used ``init``). Only ``init`` used to exist here, so
    the gear icon failed with "Handler StarlinkOptionsFlowHandler doesn't support
    step user" before the dialog could even render. Both names point at the same
    coroutine, so either core gets the cookie form.
    """

    _cookie_schema = OPTIONS_SCHEMA

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask for a cookie, or keep the stored one when the field is empty."""
        self._connect_entry_step = "user"
        if user_input is not None:
            cookie = (user_input.get(CONF_COOKIE) or "").strip()
            if not cookie:
                # Nothing typed: keep the current session, just close the dialog.
                _LOGGER.debug("Options submitted without a new cookie, keeping it")
                return self.async_create_entry(title="", data={})

            if not looks_like_cookie(cookie):
                return self._async_cookie_form(errors={"base": ERROR_INVALID_AUTH})
            return self._async_start_connect(
                cookie,
                entry_step="user",
                progress_title="Testing the new cookie",
                log_title="Starlink connection check",
            )

        return self._async_cookie_form()

    #: Older cores open the options flow on ``init``; keep that entry point.
    async_step_init = async_step_user

    def _extra_phases(self) -> tuple[str, ...]:
        """The entry is reloaded with the new cookie before the flow closes."""
        return ("reload",)

    async def _async_phase_reload(self) -> None:
        """Store the cookie, reload the entry and check the first poll."""
        probe = self._probe
        assert probe is not None
        await async_store_and_reload(
            self.hass, self.config_entry, self._connect_cookie, probe
        )
        self.async_update_progress(len(probe.results) / len(probe.phases))

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the log and close the dialog once it is submitted."""
        if user_input is None:
            return self.async_show_form(
                step_id="confirm",
                data_schema=CONFIRM_SCHEMA,
                description_placeholders={
                    "log": self._log(footer="Submit to keep the new session.")
                },
            )

        _LOGGER.info("Stored a new cookie; the entry reloaded with a successful poll")
        return self.async_create_entry(
            title="", data={CONF_COOKIE: self._connect_cookie}
        )


async def async_store_and_reload(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    cookie: str,
    probe: CookieProbe,
) -> None:
    """Store ``cookie``, reload ``entry`` and record the outcome in ``probe``.

    The coordinator keeps the HTTP client it built with the old cookie, so the
    entry has to be reloaded for the new one to be used. When the entry does not
    come back up, the previous credential is reinstated so the integration is
    left as it was found.
    """
    previous = entry.data.get(CONF_COOKIE, "")
    await async_store_cookie(hass, entry, cookie)

    await async_reload_entry(hass, entry)
    if _update_is_live(hass, entry.entry_id):
        probe.add_result(
            PhaseResult(
                "reload",
                True,
                "the entry reloaded and its first poll succeeded",
                0,
            )
        )
        return

    # The cookie passed the API check but the entry still does not come up:
    # reinstate the old credential and report the failure rather than closing the
    # dialog with a success message for a session that does not work.
    await async_store_cookie(hass, entry, previous)
    await async_reload_entry(hass, entry)
    probe.error = ERROR_CANNOT_CONNECT
    probe.add_result(
        PhaseResult(
            "reload",
            False,
            "the entry did not come back up - the previous cookie was restored",
            0,
        )
    )


async def async_reload_entry(
    hass: HomeAssistant, entry: config_entries.ConfigEntry
) -> None:
    """Reload ``entry`` without aborting the flow that asked for it.

    ``ConfigEntries.async_reload()`` aborts every re-authentication flow of the
    entry before it starts - which is this flow, when a repair or a re-auth
    dialog reloads the entry it is running in: the progress task is cancelled
    and the dialog never reaches its report. Unloading and setting up the entry
    again has the same effect on the integration (a fresh coordinator, built
    with the new cookie) and leaves the flow running.
    """
    if entry.state.recoverable:
        await hass.config_entries.async_unload(entry.entry_id)
    await hass.config_entries.async_setup(entry.entry_id)


async def async_store_cookie(
    hass: HomeAssistant, entry: config_entries.ConfigEntry, cookie: str
) -> None:
    """Store ``cookie`` in the entry and mirror it to the storage file.

    The entry is the source of truth for the cookie; the storage file is only a
    mirror that the coordinator reads when it builds its HTTP client.
    """
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_COOKIE: cookie}
    )
    await hass.async_add_executor_job(
        storage.save_cookie, hass, entry.entry_id, cookie
    )


def entry_title(hass: HomeAssistant, account: str | None) -> str:
    """Return a unique config entry title for ``account``.

    The title is shown in the entry list, in the repair issue and in the
    session-expired notification, so it names the account the entry belongs to
    whenever the cookie carries an account number. A second entry for the same
    account gets a counter: adding one twice is allowed on purpose.
    """
    base = f"{DEFAULT_TITLE} ({account[-8:]})" if account else DEFAULT_TITLE
    taken = {entry.title for entry in hass.config_entries.async_entries(DOMAIN)}
    if base not in taken:
        return base
    index = 2
    while f"{base} #{index}" in taken:
        index += 1
    return f"{base} #{index}"
