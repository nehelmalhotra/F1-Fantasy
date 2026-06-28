"""
F1 Fantasy authentication service.

Strategy (in order):
  1. Direct HTTP API calls to F1's login endpoints (fast, ~2 seconds)
  2. Headed Playwright browser as fallback (user signs in manually, ~15-30 seconds)

The direct HTTP approach works most of the time. When Imperva bot detection
blocks it, we fall back to opening a real browser window.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

FANTASY_HOME = "https://fantasy.formula1.com/"
ACCOUNT_LOGIN_URL = "https://api.formula1.com/v2/account/subscriber/authenticate/by-password"
FANTASY_SESSION_URL = "https://fantasy.formula1.com/services/session/login"
F1_API_KEY = "fCUCjWrKPu9ylJwRAv8BpGLEgiAuThx7"
DISTRIBUTION_CHANNEL = "d861e38f-05ea-4063-8776-a7e2b6d885a4"


class F1AuthError(Exception):
    pass


def guid_from_jwt(token: str) -> str | None:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        v = payload.get("007")
        return str(v) if v is not None else None
    except Exception:
        return None


def token_expiry(token: str) -> float | None:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return float(payload["exp"]) if "exp" in payload else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Strategy 1: Direct HTTP API login
# ---------------------------------------------------------------------------

def _http_login(email: str, password: str) -> tuple[str, str]:
    """
    Two-step HTTP login:
      1. POST to F1 account API -> get subscriptionToken
      2. POST to Fantasy session API with login-session cookie -> get F1_FANTASY_007
    """
    # Step 1: Account login
    resp1 = httpx.post(
        ACCOUNT_LOGIN_URL,
        json={
            "Login": email,
            "Password": password,
            "DistributionChannel": DISTRIBUTION_CHANNEL,
        },
        headers={
            "apikey": F1_API_KEY,
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
            ),
        },
        timeout=15,
    )

    if resp1.status_code == 401:
        raise F1AuthError("Invalid email or password.")
    if resp1.status_code != 200:
        raise _HttpFailed(f"Account API returned {resp1.status_code}")

    try:
        data1 = resp1.json()
    except Exception:
        raise _HttpFailed("Account API returned non-JSON response (likely bot detection)")

    # Extract subscriptionToken from response
    sub_token = None
    if isinstance(data1, dict):
        sub_token = data1.get("data", {}).get("subscriptionToken")
        if not sub_token:
            # Try alternate response shapes
            sub_token = _deep_find(data1, "subscriptionToken")
    if not sub_token:
        raise _HttpFailed("No subscriptionToken in account login response")

    # Step 2: Fantasy token exchange
    login_session_value = json.dumps({"data": {"subscriptionToken": sub_token}})
    login_session_cookie = quote(login_session_value, safe="")

    resp2 = httpx.post(
        FANTASY_SESSION_URL,
        json={
            "optType": 1,
            "platformId": 1,
            "platformVersion": "1",
            "platformCategory": "web",
            "clientId": 1,
        },
        headers={
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
            ),
            "Cookie": f"login-session={login_session_cookie}",
        },
        timeout=15,
    )

    if resp2.status_code != 200:
        raise _HttpFailed(f"Fantasy session API returned {resp2.status_code}")

    # Look for F1_FANTASY_007 in Set-Cookie headers
    f007 = None
    for val in resp2.headers.get_list("set-cookie"):
        m = re.search(r"F1_FANTASY_007=([^;]+)", val, re.I)
        if m:
            f007 = m.group(1).strip()
            break

    # Also check the JSON body
    if not f007:
        try:
            body2 = resp2.json()
            f007 = _extract_token_from_json(body2)
        except Exception:
            pass

    if not f007:
        raise _HttpFailed("No F1_FANTASY_007 token in fantasy session response")

    guid = guid_from_jwt(f007)
    if not guid:
        raise F1AuthError("Got token but could not extract user GUID from JWT.")

    return guid, f007


class _HttpFailed(Exception):
    """Internal: signals that HTTP approach failed, try Playwright fallback."""
    pass


def _deep_find(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = _deep_find(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _deep_find(item, key)
            if found is not None:
                return found
    return None


def _extract_token_from_json(data: Any) -> str | None:
    if isinstance(data, dict):
        for k, v in data.items():
            kl = str(k).lower()
            if kl in ("token", "sessiontoken", "accesstoken", "f1_fantasy_007"):
                if isinstance(v, str) and len(v) > 30 and "." in v:
                    return v.strip()
            found = _extract_token_from_json(v)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _extract_token_from_json(item)
            if found:
                return found
    return None


# ---------------------------------------------------------------------------
# Strategy 2: Playwright browser fallback (headed, user signs in manually)
# ---------------------------------------------------------------------------

_INIT_SCRIPT = """\
try {
  Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
} catch(e) {}
try {
  if (!window.chrome) window.chrome = {};
  if (!window.chrome.runtime) window.chrome.runtime = {};
} catch(e) {}
"""


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


def _collect_f007(context, page) -> str | None:
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


def _token_from_headers(headers: dict) -> str | None:
    for key, val in headers.items():
        if key.lower() != "set-cookie":
            continue
        m = re.search(r"F1_FANTASY_007=([^;]+)", str(val), re.I)
        if m:
            return m.group(1).strip()
    return None


LOGIN_URL = (
    "https://account.formula1.com/#/en/login"
    "?lead_source=web_fantasy&redirect=https%3A%2F%2Ffantasy.formula1.com%2F"
)

# Text that F1 shows when credentials are wrong (matched case-insensitively).
_BAD_CRED_PATTERNS = re.compile(
    r"(incorrect|do(es)? ?n.?t match|invalid|not recogn|problem with your "
    r"|wrong (email|password)|try again|unable to (log|sign))",
    re.I,
)


def _dismiss_consent(page, *, attempts: int = 15) -> bool:
    """
    Dismiss the Sourcepoint cookie-consent dialog that F1 renders in an iframe.

    The dialog loads slightly after the page, and while it is up it intercepts
    clicks on the sign-in button, so we poll for it for a few seconds.
    """
    for _ in range(attempts):
        # Page-level banners (in case F1 changes providers).
        for sel in (
            "#onetrust-accept-btn-handler",
            "#truste-consent-button",
            'button[title="Accept all"]',
        ):
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click(timeout=2000)
                    page.wait_for_timeout(500)
                    return True
            except Exception:
                pass
        # Sourcepoint consent iframe.
        for frame in page.frames:
            if "consent" in (frame.url or ""):
                try:
                    btn = frame.query_selector('button[title="Accept all"]')
                    if btn:
                        btn.click(timeout=3000)
                        page.wait_for_timeout(500)
                        return True
                except Exception:
                    pass
        page.wait_for_timeout(700)
    return False


def _login_error_text(page) -> str | None:
    """Return an error message if the login page is showing a credential error."""
    try:
        if "fantasy.formula1.com" in (page.url or ""):
            return None  # already redirected past login -> success path
    except Exception:
        pass
    for sel in (
        "span.control-label",
        '[class*="error"]',
        '[class*="Error"]',
        '[role="alert"]',
        ".validation-message",
    ):
        try:
            for el in page.query_selector_all(sel):
                txt = (el.inner_text() or "").strip()
                if txt and _BAD_CRED_PATTERNS.search(txt):
                    return txt
        except Exception:
            pass
    return None


def _browser_login(
    email: str,
    password: str,
    *,
    timeout_sec: float = 90.0,
    headless: bool | None = None,
) -> tuple[str, str]:
    """
    Drive a (headless) Chromium through F1's real login form, auto-filling the
    submitted credentials, and capture the ``F1_FANTASY_007`` session cookie.

    A real browser is required because F1's login is behind Imperva bot
    protection, which blocks plain HTTP requests but lets a genuine Chromium
    (even headless) execute the JS challenge and sign in normally.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise F1AuthError("Playwright is not installed") from exc

    if headless is None:
        # Allow forcing a visible window for local debugging.
        headless = os.environ.get("F1_LOGIN_HEADFUL") not in ("1", "true", "True")

    captured_token: str | None = None
    captured_guid: str | None = None
    bad_credentials = False

    def on_response(response) -> None:
        nonlocal captured_token, captured_guid, bad_credentials
        url = (response.url or "").lower()
        # F1's account auth endpoint returns 401 for wrong email/password.
        if "authenticate/by-password" in url:
            try:
                if response.status in (400, 401):
                    bad_credentials = True
            except Exception:
                pass
        if captured_token:
            return
        try:
            t = _token_from_headers(response.headers)
            if t:
                captured_token = t
                captured_guid = captured_guid or guid_from_jwt(t)
                return
        except Exception:
            pass
        if "formula1.com" not in url:
            return
        try:
            if response.status and response.status >= 400:
                return
        except Exception:
            return
        if not any(s in url for s in ("login", "session", "auth", "services", "user", "token", "account")):
            return
        try:
            ct = (response.headers.get("content-type") or "").lower()
            if "json" not in ct:
                return
            data = response.json()
            tok = _extract_token_from_json(data)
            if tok:
                captured_token = tok
                captured_guid = captured_guid or guid_from_jwt(tok)
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
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
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45_000)

            # Fill the credentials F1 expects: input[name="Login"] / input[name="Password"].
            try:
                page.wait_for_selector('input[name="Login"]', timeout=25_000)
            except Exception as exc:
                raise F1AuthError(
                    "Could not load the F1 sign-in form (F1 may be temporarily "
                    "blocking automated access). Please try again shortly."
                ) from exc

            # The consent dialog overlays the form and intercepts the submit click.
            _dismiss_consent(page)

            page.fill('input[name="Login"]', email)
            page.fill('input[name="Password"]', password)

            # The submit button is disabled until the form validates; click the
            # form's submit button (not the header "Sign in" link).
            try:
                page.click('button[type="submit"]:has-text("Sign In")', timeout=10_000)
            except Exception:
                # Fallback: re-check consent then press Enter in the password field.
                _dismiss_consent(page, attempts=3)
                try:
                    page.locator('input[name="Password"]').press("Enter")
                except Exception:
                    pass

            # Poll for the session cookie. Fail fast if F1 rejected the credentials.
            while time.monotonic() < deadline:
                if bad_credentials:
                    raise F1AuthError("Invalid email or password.")
                if captured_token:
                    break
                token = _collect_f007(context, page)
                if token:
                    captured_token = token
                    break
                time.sleep(1)

            token = captured_token or _collect_f007(context, page)
            if not token:
                if bad_credentials or _login_error_text(page):
                    raise F1AuthError("Invalid email or password.")
                raise F1AuthError(
                    "Signed in but could not capture the F1 session cookie. "
                    "This can happen if your account uses two-factor "
                    "authentication or a CAPTCHA was shown. Please try again."
                )

            guid = captured_guid or guid_from_jwt(token)
            if not guid:
                raise F1AuthError("Captured token but could not extract user GUID.")

        finally:
            try:
                browser.close()
            except Exception:
                pass

    return guid, token


# Backwards-compatible alias (was a manual-signin flow; now fully automated).
_playwright_login = _browser_login


# ---------------------------------------------------------------------------
# Public entry point: tries HTTP first, falls back to Playwright
# ---------------------------------------------------------------------------

def f1_login_sync(email: str, password: str) -> tuple[str, str]:
    """
    Authenticate with F1 Fantasy and return ``(user_guid, jwt)``.

    F1's login is behind Imperva bot protection, which reliably blocks plain
    HTTP requests (they return a "Pardon Our Interruption" page). So we drive a
    headless Chromium that auto-fills the submitted credentials and signs in
    like a real user. We still try the fast HTTP path first in case F1 ever
    relaxes the protection.
    """
    # Strategy 1: Direct HTTP (usually blocked by Imperva, but cheap to try).
    try:
        logger.info("Attempting direct HTTP login...")
        guid, token = _http_login(email, password)
        logger.info("HTTP login succeeded")
        return guid, token
    except F1AuthError:
        raise  # Real auth errors (bad password) -- don't retry with the browser.
    except _HttpFailed as exc:
        logger.info("HTTP login blocked (%s), using automated browser login", exc)

    # Strategy 2: Automated headless browser (works locally and in production;
    # the Docker image installs Chromium).
    logger.info("Running automated browser login...")
    return _browser_login(email, password)
