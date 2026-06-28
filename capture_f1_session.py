#!/usr/bin/env python3
"""
Capture F1 Fantasy session cookie after you log in with a real browser (Chromium).

Requires: pip install playwright && playwright install chromium

Modes:
  (default) Interactive: open browser, press Enter after login, print .env lines.
  --watch -o FILE: poll for F1_FANTASY_007 until found or timeout; write JSON for Streamlit import.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path


def _guid_from_jwt(token: str) -> str | None:
    try:
        payload_b64 = token.split(".")[1]
        pad = -len(payload_b64) % 4
        payload_b64 += "=" * pad
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        v = payload.get("007")
        return str(v) if v is not None else None
    except Exception:
        return None


def _write_session(path: Path, token: str) -> None:
    guid = _guid_from_jwt(token) or ""
    path.write_text(
        json.dumps({"F1_USER_GUID": guid, "F1_TOKEN": token}, indent=2),
        encoding="utf-8",
    )


def _interactive() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Install Playwright: pip install playwright && playwright install chromium", file=sys.stderr)
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://fantasy.formula1.com/", wait_until="domcontentloaded")
        print("Log in in the browser window. When you see your team / lobby, press Enter here…")
        try:
            input()
        except EOFError:
            print("No input (non-interactive); exiting.", file=sys.stderr)
            browser.close()
            sys.exit(1)

        token = _cookie_token(context)
        browser.close()

    if not token:
        print("Could not find F1_FANTASY_007 cookie. Stay on fantasy.formula1.com and stay logged in.", file=sys.stderr)
        sys.exit(1)

    guid = _guid_from_jwt(token)
    print("\n# Add or merge into .env (or paste into the Streamlit sidebar):\n")
    if guid:
        print(f"F1_USER_GUID={guid}")
    else:
        print("# F1_USER_GUID=   # set manually if auto-detect failed")
    print(f"F1_TOKEN={token}")
    print()


def _cookie_token(context) -> str | None:
    for c in context.cookies():
        if c.get("name") == "F1_FANTASY_007" and "formula1.com" in (c.get("domain") or ""):
            return c.get("value")
    return None


def _watch(output: Path, max_seconds: float, poll: float) -> None:
    try:
        from f1_playwright_login import F1LoginError, capture_session_via_f1_browser
    except ImportError:
        print("Install: pip install playwright && playwright install chromium", file=sys.stderr)
        sys.exit(1)

    try:
        guid, token = capture_session_via_f1_browser(timeout_sec=max_seconds, poll_sec=poll)
    except F1LoginError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    output.write_text(
        json.dumps({"F1_USER_GUID": guid, "F1_TOKEN": token}, indent=2),
        encoding="utf-8",
    )
    print(f"Session written to {output}", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description="Capture F1 Fantasy F1_FANTASY_007 session.")
    ap.add_argument(
        "--watch",
        action="store_true",
        help="Poll until cookie appears (for dashboard import); use with -o",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write JSON with F1_USER_GUID and F1_TOKEN (watch mode)",
    )
    ap.add_argument(
        "--max-seconds",
        type=float,
        default=900.0,
        help="Watch mode timeout (default 900)",
    )
    ap.add_argument(
        "--poll",
        type=float,
        default=2.0,
        help="Seconds between cookie checks in watch mode",
    )
    args = ap.parse_args()

    if args.watch:
        if not args.output:
            print("Watch mode requires -o /path/to/file.json", file=sys.stderr)
            sys.exit(1)
        _watch(args.output, args.max_seconds, args.poll)
        return

    if args.output:
        print("Use --watch together with -o", file=sys.stderr)
        sys.exit(1)

    _interactive()


if __name__ == "__main__":
    main()
