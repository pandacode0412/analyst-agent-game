"""Public-page browser observation; never automates betting, login, or controls."""
import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
import cv2
import numpy as np
from .config import load_regions
from .vision import analyze_frame
from .storage import connect, record_observations
from .adapters.dom import DOMStateReader, load_dom_config
from .adapters.lobby_counters import LobbyCounterReader
from .adapters.structured import StructuredExportAdapter
from .coordinator import SourceCoordinator
from uuid import uuid4
import os
from .session import (BACKOFF, CAPTCHA_REQUIRED, LOGGED_IN, LOGGED_OUT, LOGIN_FAILED,
                      NO_CREDENTIALS, SessionManager, storage_state_path)


async def capture_page(url: str, out: str, viewport_width: int, viewport_height: int, wait_ms: int) -> str:
    from playwright.async_api import async_playwright
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        try:
            page = await browser.new_page(viewport={"width": viewport_width, "height": viewport_height},
                                          device_scale_factor=1)
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(wait_ms)
            out_path = Path(out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(out_path), full_page=False)
            print(f"Screenshot: {out_path}; actual URL: {page.url}; no login attempted")
            return str(out_path)
        finally:
            await browser.close()


async def monitor_browser(url: str, config: str, database_url: str | None, output_dir: str,
                          iterations: int, interval_seconds: float,
                          width: int, height: int) -> None:
    from playwright.async_api import async_playwright
    regions = load_regions(config)
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    with connect(database_url) as conn:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
            try:
                page = await browser.new_page(viewport={"width": width, "height": height},
                                              device_scale_factor=1)
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                for frame_idx in range(iterations):
                    screenshot = await page.screenshot(full_page=False)
                    frame = cv2.imdecode(np.frombuffer(screenshot, np.uint8), cv2.IMREAD_COLOR)
                    if frame is None:
                        raise RuntimeError("Could not decode browser frame")
                    overlay, readings = analyze_frame(frame, regions)
                    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    overlay_file = outdir / f"browser_overlay_{stamp}_{frame_idx:03d}.jpg"
                    cv2.imwrite(str(overlay_file), overlay)
                    record_observations(conn, readings, str(overlay_file))
                    print(f"frame={frame_idx} page={page.url} roi_observations={readings}", flush=True)
                    if frame_idx + 1 < iterations:
                        await asyncio.sleep(interval_seconds)
            finally:
                await browser.close()


async def monitor_dom_browser(config_path: str, database_url: str | None,
                              output_dir: str, iterations: int, interval_seconds: float,
                              trusted_round_ids: bool, stop_utc: datetime | None = None,
                              login_reminder_seconds: float = 300) -> None:
    """Observe an approved DOM layout; keep unapproved IDs observation-only.

    Stops after `iterations` captures (0 = no limit) or at `stop_utc`, whichever comes first.
    """
    from playwright.async_api import async_playwright
    if iterations < 0 or interval_seconds <= 0:
        raise ValueError("iterations must be nonnegative and interval positive; zero means continuous")
    config = load_dom_config(config_path)
    reader = (LobbyCounterReader(config, output_dir) if config.reader == "lobby_counters"
              else DOMStateReader(config, output_dir))
    adapter = StructuredExportAdapter(config.source_id,
                                      trusted_round_ids=trusted_round_ids,
                                      ids_reset_per_shoe=config.ids_reset_per_shoe)
    expected = {table.table_id for table in config.tables}
    with connect(database_url) as conn:
        coordinator = SourceCoordinator(conn, config.source_id, expected,
                                        max_frame_gap_seconds=max(30, interval_seconds * 3),
                                        auto_tables=config.auto_tables)
        expected = coordinator.expected_tables  # grows when tables are discovered
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True,
                                                       args=["--disable-dev-shm-usage"])
            session = SessionManager(config.session) if config.session else None
            try:
                context, page, loaded_mtime = await _open_page(browser, config)
                completed = 0
                blocked_reason = None
                last_reminder = 0.0

                def time_left() -> bool:
                    return stop_utc is None or datetime.now(timezone.utc) < stop_utc

                while (iterations == 0 or completed < iterations) and time_left():
                    try:
                        if page.url == "about:blank":
                            await page.goto(config.url, wait_until="domcontentloaded", timeout=45000)
                        state = await session.ensure(page, context) if session else LOGGED_IN
                        if state != LOGGED_IN:
                            reason = LOGGED_OUT if state == BACKOFF else state
                            if reason != blocked_reason:
                                # One gap event per transition; continuity is broken until login.
                                stamp = datetime.now(timezone.utc).isoformat()
                                event_id = uuid4().hex
                                for table_id in expected:
                                    coordinator.gap(table_id, event_id, stamp, reason)
                                blocked_reason = reason
                            now_mono = time.monotonic()
                            if not last_reminder or now_mono - last_reminder >= login_reminder_seconds:
                                print(f"MANUAL_LOGIN_REQUIRED reason={reason} "
                                      f"at={datetime.now(timezone.utc).isoformat(timespec='seconds')}", flush=True)
                                last_reminder = now_mono
                            mtime = _state_mtime(config)
                            if mtime and mtime != loaded_mtime:
                                # A human saved a fresh session; reopen with it.
                                await context.close()
                                context, page, loaded_mtime = await _open_page(browser, config)
                        else:
                            fresh_login = session.consume_fresh_login() if session else False
                            if blocked_reason is not None or fresh_login:
                                # Login redirects elsewhere; return to the observed page once.
                                print("session_restored", flush=True)
                                blocked_reason = None
                                last_reminder = 0.0
                                await page.goto(config.url, wait_until="domcontentloaded", timeout=45000)
                            frame = await reader.capture(page)
                            statuses = coordinator.process_frame(frame, adapter)
                            print(f"frame={frame.frame_id} statuses={statuses}", flush=True)
                    except Exception as exc:
                        stamp = datetime.now(timezone.utc).isoformat()
                        event_id = uuid4().hex
                        for table_id in expected:
                            coordinator.gap(table_id, event_id, stamp, "BROWSER_OR_ADAPTER_ERROR")
                        print(f"capture_error={type(exc).__name__}; gaps_recorded={len(expected)}", flush=True)
                        if not page.is_closed():
                            try:
                                await page.goto(config.url, wait_until="domcontentloaded", timeout=45000)
                            except Exception:
                                pass
                    completed += 1
                    if (iterations == 0 or completed < iterations) and time_left():
                        await asyncio.sleep(interval_seconds)
            finally:
                await browser.close()


def _state_mtime(config) -> float | None:
    path = storage_state_path(config.session)
    return os.path.getmtime(path) if path else None


async def _open_page(browser, config):
    """Open a context, loading the saved login session when one is configured."""
    context = await browser.new_context(viewport={"width": config.width, "height": config.height},
                                        device_scale_factor=1,
                                        storage_state=storage_state_path(config.session))
    page = await context.new_page()
    return context, page, _state_mtime(config)
