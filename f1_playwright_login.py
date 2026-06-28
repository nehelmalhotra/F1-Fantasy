"""
F1 Fantasy session capture via Playwright-controlled Chromium.

Flow:
  1. Open ``fantasy.formula1.com`` (the game page, not the account page).
  2. Auto-dismiss the cookie-consent banner (iframe from consent.formula1.com).
  3. Click the **SIGN IN** button on the Fantasy page, which redirects to
     ``account.formula1.com/…?redirect=fantasy.formula1.com…``.
  4. User enters credentials. After login the site auto-redirects back to
     Fantasy, which sets the ``F1_FANTASY_007`` session cookie.
  5. We capture the cookie (via Set-Cookie interception, cookie-jar polling,
     or Chrome DevTools Protocol) and return ``(user_guid, jwt)``.

Requires: ``pip install playwright && playwright install chromium``
"""

from __future__ import annotations

import re
import time
from typing import Any

from f1_auth import extract_guid_token_from_obj, guid_from_jwt


class F1LoginError(Exception):
    """User-facing failure."""


FANTASY_HOME = "https://fantasy.formula1.com/"

_INIT_SCRIPT = """\
try {
  Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
} catch(e) {}
try {
  if (!window.chrome) window.chrome = {};
  if (!window.chrome.runtime) window.chrome.runtime = {};
} catch(e) {}
"""


# ---------------------------------------------------------------------------
# Cookie readers
# ---------------------------------------------------------------------------

def _f007_from_context(context, urls: list[str] | None = None) -> str | None:
    try:
        jar = context.cookies(urls) if urls else context.cookies()
    except Exception:
        jar = []
    for c in jar:
        if c.get("name") == "F1_FANTASY_007" and c.get("value"):
            return str(c["value"]).strip()
    return None


def _f007_via_cdp(page) -> str | None:
    try:
        cdp = page.context.new_cdp_session(page)
        try:
            result = cdp.send("Network.getAllCookies")
            for c in result.get("cookies", []):
                if c.get("name") == "F1_FANTASY_007" and c.get("value"):
                    return str(c["value"]).strip()
        finally:
            cdp.detach()
    except Exception:
        pass
    return None


def collect_f007(context, page) -> str | None:
    """Try every method to read the F1_FANTASY_007 cookie."""
    f1_urls = [
        "https://fantasy.formula1.com/",
        "https://fantasy.formula1.com",
        "https://account.formula1.com/",
    ]
    return (
        _f007_from_context(context, urls=f1_urls)
        or _f007_from_context(context)
        or _f007_via_cdp(page)
    )


# ---------------------------------------------------------------------------
# Network response helpers
# ---------------------------------------------------------------------------

def _token_from_headers(headers: dict) -> str | None:
    for key, val in headers.items():
        if key.lower() != "set-cookie":
            continue
        m = re.search(r"F1_FANTASY_007=([^;]+)", str(val), re.I)
        if m:
            return m.group(1).strip()
    return None


def _maybe_extract_from_json(data: Any) -> tuple[str | None, str | None]:
    if data is None:
        return None, None
    if isinstance(data, (str, int, float, bool)):
        return None, None
    return extract_guid_token_from_obj(data)


# ---------------------------------------------------------------------------
# Consent & sign-in helpers
# ---------------------------------------------------------------------------

def _dismiss_cookie_consent(page, timeout_ms: int = 8000) -> None:
    """Click 'Accept all' inside the consent.formula1.com iframe if present."""
    try:
        for frame in page.frames:
            if "consent" in frame.url:
                frame.click('button[title="Accept all"]', timeout=timeout_ms)
                page.wait_for_timeout(1500)
                return
    except Exception:
        pass


def _click_sign_in(page, timeout_ms: int = 5000) -> bool:
    """Click the SIGN IN button on the Fantasy homepage if present."""
    try:
        page.click('button:has-text("SIGN IN")', timeout=timeout_ms)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def capture_session_via_f1_browser(
    *,
    timeout_sec: float = 900.0,
    poll_sec: float = 1.0,
) -> tuple[str, str]:
    """Open Chromium on F1 Fantasy. User signs in; return ``(user_guid, jwt)``."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise F1LoginError(
            "Install Playwright: pip install playwright && playwright install chromium"
        ) from e

    captured_token: str | None = None
    captured_guid: str | None = None

    def on_response(response) -> None:
        nonlocal captured_token, captured_guid
        if captured_token:
            return
        # 1) Set-Cookie header on any response
        try:
            t = _token_from_headers(response.headers)
            if t:
                captured_token = t
                captured_guid = captured_guid or guid_from_jwt(t)
                return
        except Exception:
            pass

        # 2) JSON body on login/session API calls
        url = (response.url or "").lower()
        if "formula1.com" not in url:
            return
        try:
            if response.status and response.status >= 400:
                return
        except Exception:
            return
        if not any(
            s in url
            for s in ("login", "session", "auth", "services", "user", "signin", "token", "account")
        ):
            return
        try:
            ct = (response.headers.get("content-type") or "").lower()
            if "json" not in ct:
                return
            data = response.json()
            g, tok = _maybe_extract_from_json(data)
            if tok:
                captured_token = tok
                if g:
                    captured_guid = g
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1360, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )
        context.add_init_script(_INIT_SCRIPT)
        page = context.new_page()
        page.on("response", on_response)

        deadline = time.monotonic() + timeout_sec

        try:
            # --- Step 1: open Fantasy homepage ---
            page.goto(FANTASY_HOME, wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_timeout(3000)

            # Quick check: maybe user already has a session (shouldn't happen
            # in a fresh context, but costs nothing to check).
            token = captured_token or collect_f007(context, page)
            if token:
                captured_token = captured_token or token
            else:
                # --- Step 2: dismiss cookie consent ---
                _dismiss_cookie_consent(page)

                # --- Step 3: click SIGN IN (redirects to account.formula1.com
                #     with ?redirect=fantasy.formula1.com) ---
                _click_sign_in(page)
                page.wait_for_timeout(3000)

            # --- Step 4: wait for user to log in ---
            # After successful login, account.formula1.com redirects back to
            # Fantasy, which sets the F1_FANTASY_007 cookie automatically.
            while time.monotonic() < deadline:
                if captured_token:
                    break

                token = collect_f007(context, page)
                if token:
                    captured_token = token
                    break

                # If user completed login and landed back on Fantasy but
                # cookie was not captured via interception, try a reload
                # to trigger the cookie again.
                cur_url = ""
                try:
                    cur_url = (page.url or "").lower()
                except Exception:
                    pass
                if "fantasy.formula1.com" in cur_url and "account" not in cur_url:
                    token = collect_f007(context, page)
                    if token:
                        captured_token = token
                        break

                time.sleep(poll_sec)

            # --- Final collection ---
            token = captured_token or collect_f007(context, page)
            if not token:
                raise F1LoginError(
                    "Could not capture your F1 session. Make sure you signed in "
                    "**in the Chromium window that opened** (not your normal browser). "
                    "After login you should land back on Fantasy automatically. "
                    "Try **Open sign-in window** again."
                )

            guid = captured_guid or guid_from_jwt(token)
            if not guid:
                raise F1LoginError(
                    "Session cookie was captured but user ID could not be read. "
                    "Try signing in again."
                )

        finally:
            try:
                browser.close()
            except Exception:
                pass

    return guid, token
