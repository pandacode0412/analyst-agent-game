"""Session lifecycle: logged-out detection, CAPTCHA fail-closed, backoff, no secret leakage."""
import tempfile
import unittest
from pathlib import Path

from agent.session import (BACKOFF, CAPTCHA_REQUIRED, LOGGED_IN, LOGIN_FAILED, NO_CREDENTIALS,
                           SessionConfig, SessionManager, load_session_config, storage_state_path)


class FakeLocator:
    def __init__(self, page, selector):
        self.page, self.selector = page, selector

    @property
    def first(self):
        return self

    async def inner_text(self, timeout=None):
        return self.page.body

    async def count(self):
        return int("password" in self.selector and self.page.form_visible)

    async def fill(self, value, timeout=None):
        if self.page.fill_error:
            raise RuntimeError(f"fill failed for value {value}")
        self.page.filled.append(self.selector)

    async def press(self, key, timeout=None):
        self.page.submissions += 1
        self.page.after_submit(self.page)


class FakePage:
    def __init__(self, url, body="", form_visible=False, after_submit=lambda page: None):
        self.url, self.body, self.form_visible = url, body, form_visible
        self.after_submit = after_submit
        self.filled, self.submissions, self.fill_error = [], 0, False

    def locator(self, selector):
        return FakeLocator(self, selector)

    async def wait_for_timeout(self, ms):
        return None

    async def goto(self, url, **kwargs):
        self.url = url


class FakeContext:
    def __init__(self):
        self.saved = []

    async def storage_state(self, path):
        Path(path).write_text("{}", encoding="utf-8")
        self.saved.append(path)


def succeed(page):
    page.url, page.form_visible, page.body = "https://site.example/home", False, "lobby"


def captcha(page):
    page.body = "请完成安全验证 请依次点击"


CREDS = {"SITE_USERNAME": "owner", "SITE_PASSWORD": "secret-value"}


class SessionTests(unittest.IsolatedAsyncioTestCase):
    def manager(self, environ=CREDS, clock=None, storage=""):
        config = SessionConfig(storage_state=storage, captcha_pattern="请完成安全验证|captcha",
                               relogin_backoff_seconds=600)
        times = clock or [0.0]
        return SessionManager(config, clock=lambda: times[0], environ=environ), times

    async def test_logged_in_page_needs_nothing(self):
        manager, _ = self.manager()
        page = FakePage("https://site.example/home", "lobby")
        self.assertEqual(await manager.ensure(page, FakeContext()), LOGGED_IN)
        self.assertEqual(page.submissions, 0)

    async def test_relogin_without_captcha_saves_session(self):
        with tempfile.TemporaryDirectory() as folder:
            state = str(Path(folder) / "nested" / "session_state.json")
            manager, _ = self.manager(storage=state)
            context = FakeContext()
            page = FakePage("https://site.example/login", form_visible=True, after_submit=succeed)
            self.assertEqual(await manager.ensure(page, context), LOGGED_IN)
            self.assertEqual(context.saved, [state])
            self.assertEqual(storage_state_path(manager.config), state)
            self.assertTrue(manager.consume_fresh_login())
            self.assertFalse(manager.consume_fresh_login())

    async def test_captcha_fails_closed_without_interaction(self):
        manager, _ = self.manager()
        page = FakePage("https://site.example/login", body="请完成安全验证", form_visible=True)
        self.assertEqual(await manager.ensure(page, FakeContext()), CAPTCHA_REQUIRED)
        self.assertEqual((page.filled, page.submissions), ([], 0))

    async def test_captcha_after_submit_is_reported_and_backoff_applies(self):
        manager, times = self.manager()
        page = FakePage("https://site.example/login", form_visible=True, after_submit=captcha)
        self.assertEqual(await manager.ensure(page, FakeContext()), CAPTCHA_REQUIRED)
        page.body = ""  # human closed the CAPTCHA; still logged out
        times[0] = 100
        self.assertEqual(await manager.ensure(page, FakeContext()), BACKOFF)
        self.assertEqual(page.submissions, 1)
        times[0] = 700
        await manager.ensure(page, FakeContext())
        self.assertEqual(page.submissions, 2)

    async def test_missing_credentials_and_fill_errors_do_not_leak(self):
        manager, _ = self.manager(environ={})
        page = FakePage("https://site.example/login", form_visible=True)
        self.assertEqual(await manager.ensure(page, FakeContext()), NO_CREDENTIALS)
        manager, _ = self.manager()
        page = FakePage("https://site.example/login", form_visible=True)
        page.fill_error = True
        self.assertEqual(await manager.ensure(page, FakeContext()), LOGIN_FAILED)

    async def test_still_on_login_after_submit_is_failure(self):
        manager, _ = self.manager()
        page = FakePage("https://site.example/login", form_visible=True)
        self.assertEqual(await manager.ensure(page, FakeContext()), LOGIN_FAILED)

    def test_config_validation(self):
        self.assertIsNone(load_session_config(None))
        config = load_session_config({"storage_state": "secrets/s.json", "relogin_backoff_seconds": 900})
        self.assertEqual(config.relogin_backoff_seconds, 900.0)
        for bad in ({"unknown": 1}, {"relogin_backoff_seconds": 5}, {"login_url": "ftp://x"},
                    {"captcha_pattern": "("}, "not-a-dict"):
            with self.assertRaises(Exception, msg=bad):
                load_session_config(bad)


if __name__ == "__main__":
    unittest.main()
