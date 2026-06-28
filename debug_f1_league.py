#!/usr/bin/env python3
"""
Local probe for F1 Fantasy API (same URLs as app.py). Loads .env — does not print tokens.

Usage:
  cd /Users/personal/Projects/F1-Fantasy && source f1_env/bin/activate && python debug_f1_league.py

Optional: F1_LEAGUE_ID=12345678 in .env (defaults to LEAGUE_ID in app if unset — edit script or set env).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Default league id must match app.py if you don't set F1_LEAGUE_ID
_DEFAULT_LEAGUE_ID = 10328108


def _summarize_json(data: dict) -> str:
    if not isinstance(data, dict):
        return f"type={type(data).__name__}"
    keys = list(data.keys())
    d = data.get("Data")
    out = [f"top_keys={keys}"]
    if d is None:
        out.append("Data=None")
    elif isinstance(d, dict):
        v = d.get("Value")
        out.append(f"Data.keys={list(d.keys())}")
        if v is None:
            out.append("Value=None")
        elif isinstance(v, dict):
            mr = v.get("memRank")
            out.append(f"Value.keys={list(v.keys())}")
            out.append(f"memRank type={type(mr).__name__} len={len(mr) if isinstance(mr, list) else 'n/a'}")
        else:
            out.append(f"Value type={type(v).__name__}")
    else:
        out.append(f"Data type={type(d).__name__}")
    return " | ".join(out)


async def main() -> int:
    root = Path(__file__).resolve().parent
    load_dotenv(root / ".env")

    guid = (os.environ.get("F1_USER_GUID") or "").strip()
    token = (os.environ.get("F1_TOKEN") or "").strip()
    league_id = int(os.environ.get("F1_LEAGUE_ID") or _DEFAULT_LEAGUE_ID)

    print("=== F1 Fantasy API debug ===")
    print(f"LEAGUE_ID={league_id} (set F1_LEAGUE_ID in .env to override)")
    print(f"F1_USER_GUID set: {bool(guid)} (length {len(guid)})")
    print(f"F1_TOKEN set: {bool(token)} (length {len(token) if token else 0})")

    if not guid or not token:
        print("\nERROR: F1_USER_GUID and F1_TOKEN must be set in .env")
        return 1

    base = "https://fantasy.formula1.com"
    roster_url = (
        f"/services/user/leaderboard/{guid}/pvtleagueuserrankget/1/{league_id}/0/1/1/100/"
    )
    race1_url = (
        f"/services/user/leaderboard/{guid}/pvtleagueuserrankget/2/{league_id}/1/1/1/100/"
    )

    async with httpx.AsyncClient(
        base_url=base,
        cookies={"F1_FANTASY_007": token},
        timeout=30.0,
    ) as client:
        for name, path in [("roster (type 1)", roster_url), ("race 1 points (type 2)", race1_url)]:
            print(f"\n--- GET {name} ---")
            try:
                r = await client.get(path)
            except httpx.RequestError as e:
                print(f"REQUEST FAILED: {e}")
                continue
            print(f"HTTP {r.status_code}")
            ct = r.headers.get("content-type", "")
            print(f"content-type: {ct[:80]}")
            if r.status_code != 200:
                body_preview = (r.text or "")[:500]
                print(f"body preview: {body_preview!r}")
                continue
            try:
                data = r.json()
            except json.JSONDecodeError:
                print("body is not JSON")
                print((r.text or "")[:500])
                continue
            print(_summarize_json(data))

    print("\n=== done ===")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
