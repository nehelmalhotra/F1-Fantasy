"""Automatic CAPTCHA solving for the F1 login, via 2Captcha.

F1's login sits behind Imperva bot protection, which sometimes shows a
CAPTCHA (reCAPTCHA / hCaptcha / Arkose FunCaptcha / Cloudflare Turnstile)
that headless Chromium cannot pass on its own. This module detects whichever
widget appears on the page, sends it to 2Captcha, and injects the solution
token back into the page so the login continues — fully automated, no user
action, no DevTools.

Setup (one time):
  1. Create an account at https://2captcha.com and top it up. A few dollars
     lasts months here: roughly one solve every few days at ~$0.003 each.
  2. Set CAPTCHA_API_KEY to your 2Captcha API key in the backend's
     environment (Render dashboard -> Environment). The backend picks it up
     on the next deploy/restart.

If CAPTCHA_API_KEY is unset, solve_captcha_if_present() simply returns False
and the login behaves exactly as before (may fail on CAPTCHA with the usual
"try again" error).
"""

from __future__ import annotations

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

_IN_URL = "https://2captcha.com/in.php"
_RES_URL = "https://2captcha.com/res.php"
_POLL_INTERVAL = 5
_POLL_TIMEOUT = 180


def _api_key() -> str:
    return os.environ.get("CAPTCHA_API_KEY", "").strip()


# One JS probe that detects whichever known CAPTCHA widget is on the page.
_DETECT_JS = """() => {
  const html = document.documentElement.innerHTML;
  const sitekey = () => {
    const m = html.match(/data-sitekey="([^"]+)"/);
    return m ? m[1] : null;
  };
  // reCAPTCHA v2 (checkbox / invisible)
  if (document.querySelector('.g-recaptcha[data-sitekey]'))
    return {kind: 'recaptcha2', sitekey: document.querySelector('.g-recaptcha[data-sitekey]').getAttribute('data-sitekey')};
  if (document.querySelector('iframe[src*="recaptcha/api2/anchor"], iframe[src*="recaptcha/enterprise/anchor"]'))
    return {kind: 'recaptcha2', sitekey: sitekey()};
  // hCaptcha
  if (document.querySelector('.h-captcha[data-sitekey]'))
    return {kind: 'hcaptcha', sitekey: document.querySelector('.h-captcha[data-sitekey]').getAttribute('data-sitekey')};
  if (document.querySelector('iframe[src*="hcaptcha.com/captcha"]'))
    return {kind: 'hcaptcha', sitekey: sitekey()};
  // Arkose FunCaptcha
  if (document.querySelector('iframe[src*="funcaptcha"], iframe[src*="arkoselabs"]')) {
    const m = html.match(/data-pkey="([^"]+)"/) || html.match(/publicKey["']?\\s*:\\s*["']([^"']+)/);
    return {kind: 'funcaptcha', sitekey: m ? m[1] : null};
  }
  // Cloudflare Turnstile
  if (document.querySelector('.cf-turnstile[data-sitekey]'))
    return {kind: 'turnstile', sitekey: document.querySelector('.cf-turnstile[data-sitekey]').getAttribute('data-sitekey')};
  if (document.querySelector('iframe[src*="challenges.cloudflare.com"]'))
    return {kind: 'turnstile', sitekey: sitekey()};
  return {kind: null, sitekey: null};
}"""

# Token injection per widget type. Each snippet receives the solution token.
_INJECT_JS = {
    "recaptcha2": """(token) => {
      const set = (sel) => { const el = document.querySelector(sel); if (el) { el.innerHTML = token; el.value = token; } };
      set('#g-recaptcha-response'); set('[name="g-recaptcha-response"]');
      try {
        const cfg = window.___grecaptcha_cfg;
        if (cfg && cfg.clients) for (const k of Object.keys(cfg.clients)) {
          const c = cfg.clients[k];
          const cb = c && (c.callback || (c.L && c.L.callback));
          if (typeof cb === 'function') cb(token);
          else if (typeof cb === 'string' && typeof window[cb] === 'function') window[cb](token);
        }
      } catch (e) {}
    }""",
    "hcaptcha": """(token) => {
      const set = (sel) => { const el = document.querySelector(sel); if (el) { el.innerHTML = token; el.value = token; } };
      set('[name="h-captcha-response"]'); set('[data-hcaptcha-response]');
      try {
        const ev = new Event('input', {bubbles: true});
        document.querySelectorAll('[name="h-captcha-response"]').forEach(el => el.dispatchEvent(ev));
      } catch (e) {}
    }""",
    "turnstile": """(token) => {
      const set = (sel) => { const el = document.querySelector(sel); if (el) { el.innerHTML = token; el.value = token; } };
      set('[name="cf-turnstile-response"]');
    }""",
    # Arkose: best effort — expose the token where common integrations look.
    "funcaptcha": """(token) => {
      window.fcToken = token;
      const el = document.querySelector('[name="fc-token"]');
      if (el) { el.value = token; }
    }""",
}


def _params_for(kind: str, sitekey: str, page_url: str) -> dict | None:
    if kind == "recaptcha2":
        return {"method": "userrecaptcha", "googlekey": sitekey, "pageurl": page_url}
    if kind == "hcaptcha":
        return {"method": "hcaptcha", "sitekey": sitekey, "pageurl": page_url}
    if kind == "turnstile":
        return {"method": "turnstile", "sitekey": sitekey, "pageurl": page_url}
    if kind == "funcaptcha":
        return {
            "method": "funcaptcha",
            "publickey": sitekey,
            "pageurl": page_url,
            "surl": "https://client-api.arkoselabs.com",
        }
    return None


def _submit(params: dict, api_key: str) -> str | None:
    try:
        body = httpx.post(_IN_URL, data={"key": api_key, **params}, timeout=20).text
    except Exception as exc:
        logger.warning("2Captcha submit failed: %s", exc)
        return None
    if body.startswith("OK|"):
        return body[3:].strip()
    logger.warning("2Captcha submit rejected: %s", body[:200])
    return None


def _poll(task_id: str, api_key: str) -> str | None:
    deadline = time.monotonic() + _POLL_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL)
        try:
            body = httpx.get(
                _RES_URL,
                params={"key": api_key, "action": "get", "id": task_id},
                timeout=20,
            ).text
        except Exception:
            continue
        if body.startswith("OK|"):
            return body[3:].strip()
        if body != "CAPCHA_NOT_READY":  # 2Captcha's spelling, not ours
            logger.warning("2Captcha poll error: %s", body[:200])
            return None
    logger.warning("2Captcha solve timed out after %ss", _POLL_TIMEOUT)
    return None


def solve_captcha_if_present(page) -> bool:
    """Detect a CAPTCHA widget on the page and solve it via 2Captcha.

    Returns True if a widget was found and a solution token was injected,
    False otherwise (no widget, no API key, or solve failed). Never raises.
    """
    api_key = _api_key()
    if not api_key:
        return False
    try:
        info = page.evaluate(_DETECT_JS) or {}
    except Exception:
        return False
    kind, sitekey = info.get("kind"), info.get("sitekey")
    if not kind:
        return False
    if not sitekey:
        logger.warning("Found a %s widget but no sitekey; cannot solve", kind)
        return False
    params = _params_for(kind, sitekey, page.url or "")
    if not params:
        return False
    logger.info("CAPTCHA detected (%s); solving via 2Captcha...", kind)
    task_id = _submit(params, api_key)
    if not task_id:
        return False
    token = _poll(task_id, api_key)
    if not token:
        return False
    try:
        page.evaluate(_INJECT_JS[kind], token)
    except Exception as exc:
        logger.warning("Failed to inject CAPTCHA token: %s", exc)
        return False
    logger.info("CAPTCHA (%s) solved and injected", kind)
    return True
