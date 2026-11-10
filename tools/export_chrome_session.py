"""Export a human-logged-in session from a real Chrome into Playwright storage-state format.

Use when a site rejects logins from an automated browser (docs/17-source-integration.md).
Start Chrome with a separate profile and a local debug port, log in by hand (including any
CAPTCHA), then run, for example inside Docker:

    python tools/export_chrome_session.py --origin-contains example-site --out secrets/session_state.json

The tool attaches read-only, never clicks, never closes the browser, and prints only counts.
Cookies and localStorage are written to the output file, which must stay in ignored secrets/.
"""
import argparse
import asyncio
import json
import os
import socket


async def export(cdp_host: str, port: int, origin_contains: str, out: str) -> dict:
    from playwright.async_api import async_playwright
    ip = socket.gethostbyname(cdp_host)  # Chrome rejects non-IP Host headers on the debug port
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(f"http://{ip}:{port}")
        context = browser.contexts[0]
        page = next((pg for pg in context.pages if origin_contains in pg.url), None)
        if page is None:
            raise SystemExit(f"no open tab whose URL contains {origin_contains!r}")
        origin = await page.evaluate("location.origin")
        if "/login" in page.url:
            raise SystemExit("the tab is still on a login page; finish logging in first")
        local = await page.evaluate(
            "() => Object.entries(localStorage).map(([name, value]) => ({name, value}))")
        cookies = await context.cookies()
        state = {"cookies": cookies, "origins": [{"origin": origin, "localStorage": local}]}
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out + ".tmp", "w", encoding="utf-8") as handle:
            json.dump(state, handle)
        os.replace(out + ".tmp", out)
        # Deliberately no browser.close(): it would affect the operator's Chrome.
        return {"origin": origin, "cookies": len(cookies), "local_storage_keys": len(local), "out": out}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cdp-host", default="host.docker.internal",
                        help="Host running Chrome; use 127.0.0.1 outside Docker")
    parser.add_argument("--port", type=int, default=9222)
    parser.add_argument("--origin-contains", required=True, help="Substring of the logged-in tab URL")
    parser.add_argument("--out", default="secrets/session_state.json")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(export(args.cdp_host, args.port, args.origin_contains, args.out))))


if __name__ == "__main__":
    main()
