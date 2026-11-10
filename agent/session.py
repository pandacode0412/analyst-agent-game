"""Optional login-session lifecycle for monitor-dom (docs/17-source-integration.md).

A human performs the first login and solves every CAPTCHA. This module only
reuses a saved storage state, detects logged-out pages, and re-submits the
owner's credentials when no CAPTCHA is shown. It never interacts with a CAPTCHA
and never prints credentials.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import re
import time

LOGGED_IN = "LOGGED_IN"
LOGGED_OUT = "LOGGED_OUT"
CAPTCHA_REQUIRED = "CAPTCHA_REQUIRED"
LOGIN_FAILED = "LOGIN_FAILED"
NO_CREDENTIALS = "NO_CREDENTIALS"
BACKOFF = "BACKOFF"


@dataclass(frozen=True)
class SessionConfig:
    storage_state: str = ""
    login_url: str = ""
    logged_out_url_fragment: str = "/login"
    required_url_fragment: str = ""
    username_selector: str = "input[type=text]"
    password_selector: str = "input[type=password]"
    captcha_pattern: str = "captcha"
    relogin_backoff_seconds: float = 600
    username_env: str = "SITE_USERNAME"
    password_env: str = "SITE_PASSWORD"


def load_session_config(block) -> SessionConfig | None:
    """Parse the optional `session` block of a DOM config."""
    if block is None:
        return None
    if not isinstance(block, dict):
        raise ValueError("session must be an object")
    allowed = set(SessionConfig.__dataclass_fields__)
    unknown = set(block) - allowed
    if unknown:
        raise ValueError(f"unknown session fields: {', '.join(sorted(unknown))}")
    values = {key: (float(value) if key == "relogin_backoff_seconds" else str(value).strip())
              for key, value in block.items()}
    config = SessionConfig(**values)
    if config.login_url and not config.login_url.startswith(("https://", "http://")):
        raise ValueError("session.login_url must be HTTP(S)")
    if config.relogin_backoff_seconds < 60:
        raise ValueError("session.relogin_backoff_seconds must be at least 60")
    re.compile(config.captcha_pattern)
    return config


def storage_state_path(config: SessionConfig | None) -> str | None:
    """Return the saved session path if it exists, else None."""
    if config and config.storage_state and Path(config.storage_state).is_file():
        return config.storage_state
    return None


async def _visible_text(page) -> str:
    try:
        return await page.locator("body").inner_text(timeout=3000)
    except Exception:
        return ""


async def login_state(page, config: SessionConfig, require_target: bool = True) -> str:
    """Classify the current page as LOGGED_IN, LOGGED_OUT, or CAPTCHA_REQUIRED."""
    text = await _visible_text(page)
    if re.search(config.captcha_pattern, text, re.IGNORECASE):
        return CAPTCHA_REQUIRED
    if config.logged_out_url_fragment and config.logged_out_url_fragment in page.url:
        return LOGGED_OUT
    if require_target and config.required_url_fragment and config.required_url_fragment not in page.url:
        # Some sites redirect a logged-out visitor to the home page, not to /login.
        return LOGGED_OUT
    try:
        if await page.locator(f"{config.password_selector}:visible").count():
            return LOGGED_OUT
    except Exception:
        pass
    return LOGGED_IN


class SessionManager:
    """Decide when re-login may be attempted and perform it without touching a CAPTCHA."""

    def __init__(self, config: SessionConfig, *, clock=time.monotonic, environ=os.environ):
        self.config = config
        self._clock = clock
        self._environ = environ
        self._last_attempt: float | None = None
        self._fresh_login = False

    def _credentials(self) -> tuple[str, str] | None:
        user = self._environ.get(self.config.username_env, "")
        password = self._environ.get(self.config.password_env, "")
        return (user, password) if user and password else None

    def consume_fresh_login(self) -> bool:
        """True once after this manager logged in; the caller should reopen the observed page."""
        fresh, self._fresh_login = self._fresh_login, False
        return fresh

    async def ensure(self, page, context) -> str:
        """Return LOGGED_IN or the reason observation must not proceed."""
        state = await login_state(page, self.config)
        if state == LOGGED_IN:
            return LOGGED_IN
        if state == CAPTCHA_REQUIRED:
            return CAPTCHA_REQUIRED
        now = self._clock()
        if self._last_attempt is not None and now - self._last_attempt < self.config.relogin_backoff_seconds:
            return BACKOFF
        credentials = self._credentials()
        if credentials is None:
            return NO_CREDENTIALS
        self._last_attempt = now
        if self.config.login_url and self.config.logged_out_url_fragment not in page.url:
            await page.goto(self.config.login_url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(3000)
        try:
            await page.locator(f"{self.config.username_selector}:visible").first.fill(credentials[0], timeout=5000)
            password = page.locator(f"{self.config.password_selector}:visible").first
            await password.fill(credentials[1], timeout=5000)
            await password.press("Enter", timeout=5000)
        except Exception:
            # Playwright errors can echo filled values; report only the outcome.
            return LOGIN_FAILED
        await page.wait_for_timeout(6000)
        # The site may land on its home page after login; the caller reopens the target URL.
        state = await login_state(page, self.config, require_target=False)
        if state == CAPTCHA_REQUIRED:
            return CAPTCHA_REQUIRED
        if state != LOGGED_IN:
            return LOGIN_FAILED
        if self.config.storage_state:
            Path(self.config.storage_state).parent.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=self.config.storage_state)
        self._fresh_login = True
        return LOGGED_IN
