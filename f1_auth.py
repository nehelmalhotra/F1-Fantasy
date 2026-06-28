"""
Parse F1 Fantasy session material from DevTools (Network) or cookie strings.

There is no public OAuth for fantasy.formula1.com; community clients (e.g. skelmis-f1-fantasy)
use the session login response or the F1_FANTASY_007 cookie. This module normalizes that.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any


def guid_from_jwt(token: str) -> str | None:
    """Decode user id from JWT payload claim ``007`` if present."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        pad = -len(payload_b64) % 4
        payload_b64 += "=" * pad
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        v = payload.get("007")
        return str(v) if v is not None else None
    except Exception:
        return None


def _coerce_guid(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return str(val)
    if isinstance(val, str) and val.strip().isdigit():
        return val.strip()
    return None


def _coerce_token(val: Any) -> str | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, str) and len(val) > 30 and "." in val:
        return val.strip()
    return None


def extract_guid_token_from_obj(obj: Any) -> tuple[str | None, str | None]:
    """Walk nested dict/list for GUID + Token-like fields (login API responses vary)."""
    guid: str | None = None
    token: str | None = None

    def walk(x: Any) -> None:
        nonlocal guid, token
        if isinstance(x, dict):
            for k, v in x.items():
                kl = str(k).lower()
                if kl in ("guid", "userguid", "user_guid", "global_id"):
                    g = _coerce_guid(v)
                    if g:
                        guid = guid or g
                if kl in ("token", "sessiontoken", "accesstoken", "f1_fantasy_007"):
                    t = _coerce_token(v)
                    if t:
                        token = token or t
                if kl == "007" and isinstance(v, (str, int)):
                    g = _coerce_guid(v)
                    if g:
                        guid = guid or g
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(obj)
    return guid, token


def parse_login_json_text(text: str) -> tuple[str | None, str | None, str | None]:
    """
    Parse pasted DevTools response body (JSON).

    Returns (guid, token, error_message).
    """
    raw = text.strip()
    if not raw:
        return None, None, "Paste is empty."
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, None, f"Not valid JSON: {e}"

    guid, token = extract_guid_token_from_obj(obj)
    if not token:
        return None, None, "Could not find a session token in the JSON (look for Token or similar)."
    if not guid:
        guid = guid_from_jwt(token)
    if not guid:
        return None, token, "Found token but not GUID — paste your numeric User GUID manually."
    return guid, token, None


def parse_cookie_or_header(text: str) -> tuple[str | None, str | None, str | None]:
    """
    Parse ``F1_FANTASY_007=...`` or a Cookie header line containing that cookie.

    Returns (guid, token, error_message).
    """
    raw = text.strip()
    if not raw:
        return None, None, "Paste is empty."

    m = re.search(r"F1_FANTASY_007\s*=\s*([^;\s]+)", raw, re.I)
    if not m:
        return None, None, "No F1_FANTASY_007 cookie found in the text."
    token = unquote_cookie(m.group(1))
    guid = guid_from_jwt(token)
    if not guid:
        return None, token, "Parsed cookie but could not read User GUID from JWT — enter GUID manually."
    return guid, token, None


def unquote_cookie(val: str) -> str:
    try:
        from urllib.parse import unquote

        return unquote(val)
    except Exception:
        return val


def parse_session_paste(text: str) -> tuple[str | None, str | None, str | None]:
    """
    Try JSON login response, then cookie line, then a raw JWT string.

    Returns (guid, token, error_message).
    """
    raw = (text or "").strip()
    if not raw:
        return None, None, "Paste is empty."
    if raw.startswith("{"):
        return parse_login_json_text(raw)
    if "F1_FANTASY_007" in raw:
        return parse_cookie_or_header(raw)
    parts = raw.split(".")
    if len(parts) == 3 and len(raw) > 40:
        guid = guid_from_jwt(raw)
        if guid:
            return guid, raw, None
        return None, raw, "JWT found but could not read User GUID (007); add GUID manually."
    return (
        None,
        None,
        "Paste JSON from DevTools → Network → `/services/session/login` → Response, "
        "or a line containing `F1_FANTASY_007=…`.",
    )
