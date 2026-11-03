"""One Chromium for the process, and a fresh context per page."""

from __future__ import annotations

from playwright.sync_api import Browser, Page, Playwright, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from interface_compiler import __version__

# Chromium's own user agent, plus this suffix. The leading space is part of it.
USER_AGENT_SUFFIX = (
    f" interface-compiler/{__version__} (+https://github.com/akashnaren/interface-compiler)"
)
VIEWPORT = {"width": 1280, "height": 800}
_SANDBOX_UNAVAILABLE = (
    "Chromium sandbox is unavailable. Enable unprivileged user namespaces "
    "(kernel.apparmor_restrict_unprivileged_userns=0) and start again."
)


def _pipe_closed(exc: BaseException) -> bool:
    return "connection closed" in str(exc).lower()


def _driver_already_stopped(exc: BaseException) -> bool:
    """True when Playwright is reporting a driver this process already stopped."""
    text = str(exc).lower()
    return _pipe_closed(exc) or "has been closed" in text or "target closed" in text


def _sandbox_unavailable(exc: BaseException) -> bool:
    return "sandbox" in str(exc).lower()


class Engine:
    """Headless Chromium. Each `new_page` gets an ephemeral context.

    The CLI constructs an engine and closes it before the process exits.
    Closing Chromium is what lets `interface-compiler raw` finish. Tests keep
    a separate engine for the session and should not call the CLI in-process,
    because that invocation closes only the browser it started.
    """

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._user_agent: str | None = None

    @property
    def user_agent(self) -> str:
        if self._user_agent is None:
            raise RuntimeError("browser is not started")
        return self._user_agent

    def start(self) -> None:
        if self._browser is not None:
            raise RuntimeError("browser is already started")
        playwright = sync_playwright().start()
        self._playwright = playwright
        try:
            browser = playwright.chromium.launch(headless=True, chromium_sandbox=True)
        except PlaywrightError as exc:
            self.close()
            if _sandbox_unavailable(exc):
                raise RuntimeError(_SANDBOX_UNAVAILABLE) from exc
            raise
        self._browser = browser
        session = browser.new_browser_cdp_session()
        try:
            version = session.send("Browser.getVersion")
        finally:
            session.detach()
        default_ua = version.get("userAgent") if isinstance(version, dict) else None
        if not isinstance(default_ua, str) or not default_ua:
            self.close()
            raise RuntimeError("browser did not report a user agent")
        self._user_agent = f"{default_ua}{USER_AGENT_SUFFIX}"

    def new_page(self) -> Page:
        if self._browser is None:
            raise RuntimeError("browser is not started")
        context = self._browser.new_context(
            viewport=VIEWPORT,
            locale="en-US",
            user_agent=self.user_agent,
            accept_downloads=False,
            service_workers="block",
        )
        return context.new_page()

    def close(self) -> None:
        browser = self._browser
        playwright = self._playwright
        self._browser = None
        self._playwright = None
        self._user_agent = None
        failure: Exception | None = None
        driver_gone = False
        if browser is not None:
            try:
                browser.close()
            except Exception as exc:  # noqa: BLE001  Playwright raises Exception for a dead driver.
                if _pipe_closed(exc):
                    driver_gone = True
                elif not _driver_already_stopped(exc):
                    failure = exc
        # A killed driver has already closed the pipe. stop() would wait on it.
        if playwright is not None and not driver_gone:
            try:
                playwright.stop()
            except Exception as exc:  # noqa: BLE001  Playwright raises Exception for a dead driver.
                if failure is None and not _driver_already_stopped(exc):
                    failure = exc
        if failure is not None:
            raise failure
