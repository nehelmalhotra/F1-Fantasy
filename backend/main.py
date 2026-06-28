"""
FastAPI backend for F1 Fantasy Dashboard.

Endpoints:
  Auth:   POST /api/auth/f1-login, GET /api/auth/me, POST /api/auth/logout
  Data:   GET /api/league/{id}/standings, races, budget, chips, members
  Misc:   GET /api/schedule
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

import pytz
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load environment variables from a local .env (backend/.env first, then repo root).
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from db import (
    init_db,
    upsert_user,
    upsert_user_league,
    get_user_by_guid,
    get_user_by_id,
    get_user_leagues,
    get_league_members,
    get_league_member_names,
    get_race_results,
    get_budget_history,
    get_chip_usage,
    get_collected_rounds,
    get_users_with_valid_tokens,
)
from f1_auth_service import f1_login_sync, F1AuthError, guid_from_jwt, token_expiry
from collect_data import collect_league_data

logger = logging.getLogger(__name__)

app = FastAPI(title="F1 Fantasy API", version="1.0.0")

FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


# ---------------------------------------------------------------------------
# Session management (signed cookie)
# ---------------------------------------------------------------------------
SESSION_COOKIE = "f1dash_session"
SECRET = os.environ.get("SESSION_SECRET", "change-me-in-production")


IS_PROD = os.environ.get("ENV") == "production"
# Frontend and backend live on different domains in production (Vercel + Railway),
# so the session cookie must be SameSite=None; Secure to be sent cross-site.
_COOKIE_SAMESITE = "none" if IS_PROD else "lax"


def _set_session(response: Response, user_id: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        value=str(user_id),
        httponly=True,
        samesite=_COOKIE_SAMESITE,
        max_age=60 * 60 * 24 * 30,
        secure=IS_PROD,
    )


def _get_session_user_id(request: Request) -> int | None:
    val = request.cookies.get(SESSION_COOKIE)
    if val and val.isdigit():
        return int(val)
    return None


def _require_session(request: Request) -> dict:
    uid = _get_session_user_id(request)
    if uid is None:
        raise HTTPException(401, "Not authenticated")
    user = get_user_by_id(uid)
    if not user:
        raise HTTPException(401, "User not found")
    return user


# ---------------------------------------------------------------------------
# 2026 F1 Calendar
# ---------------------------------------------------------------------------
F1_SCHEDULE = [
    {"round": 1,  "name": "Australia",          "location": "Melbourne",      "date": "2026-03-08", "time": "04:00", "sprint": False},
    {"round": 2,  "name": "China",              "location": "Shanghai",       "date": "2026-03-15", "time": "07:00", "sprint": True},
    {"round": 3,  "name": "Japan",              "location": "Suzuka",         "date": "2026-03-29", "time": "05:00", "sprint": False},
    {"round": 4,  "name": "Miami",              "location": "Miami",          "date": "2026-05-03", "time": "20:00", "sprint": True},
    {"round": 5,  "name": "Canada",             "location": "Montreal",       "date": "2026-05-24", "time": "20:00", "sprint": True},
    {"round": 6,  "name": "Monaco",             "location": "Monte Carlo",    "date": "2026-06-07", "time": "13:00", "sprint": False},
    {"round": 7,  "name": "Barcelona-Catalunya", "location": "Barcelona",     "date": "2026-06-14", "time": "13:00", "sprint": False},
    {"round": 8,  "name": "Austria",            "location": "Spielberg",      "date": "2026-06-28", "time": "13:00", "sprint": False},
    {"round": 9,  "name": "Great Britain",      "location": "Silverstone",    "date": "2026-07-05", "time": "14:00", "sprint": True},
    {"round": 10, "name": "Belgium",            "location": "Spa",            "date": "2026-07-19", "time": "13:00", "sprint": False},
    {"round": 11, "name": "Hungary",            "location": "Budapest",       "date": "2026-07-26", "time": "13:00", "sprint": False},
    {"round": 12, "name": "Netherlands",        "location": "Zandvoort",      "date": "2026-08-23", "time": "13:00", "sprint": True},
    {"round": 13, "name": "Italy",              "location": "Monza",          "date": "2026-09-06", "time": "13:00", "sprint": False},
    {"round": 14, "name": "Spain",              "location": "Madrid",         "date": "2026-09-13", "time": "13:00", "sprint": False},
    {"round": 15, "name": "Azerbaijan",         "location": "Baku",           "date": "2026-09-26", "time": "11:00", "sprint": False},
    {"round": 16, "name": "Singapore",          "location": "Marina Bay",     "date": "2026-10-11", "time": "12:00", "sprint": True},
    {"round": 17, "name": "United States",      "location": "Austin",         "date": "2026-10-25", "time": "20:00", "sprint": False},
    {"round": 18, "name": "Mexico",             "location": "Mexico City",    "date": "2026-11-01", "time": "20:00", "sprint": False},
    {"round": 19, "name": "Brazil",             "location": "Sao Paulo",      "date": "2026-11-08", "time": "17:00", "sprint": False},
    {"round": 20, "name": "Las Vegas",          "location": "Las Vegas",      "date": "2026-11-22", "time": "04:00", "sprint": False},
    {"round": 21, "name": "Qatar",              "location": "Lusail",         "date": "2026-11-29", "time": "16:00", "sprint": False},
    {"round": 22, "name": "Abu Dhabi",          "location": "Yas Marina",     "date": "2026-12-06", "time": "13:00", "sprint": False},
]

RACE_NAMES = {r["round"]: r["name"] for r in F1_SCHEDULE}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
DEFAULT_LEAGUE_ID = int(os.environ.get("F1_LEAGUE_ID") or 10328108)


class LoginRequest(BaseModel):
    # All optional: blank fields fall back to credentials stored in .env,
    # so you can sign in locally without re-typing them every time.
    email: str | None = None
    password: str | None = None
    league_id: int | None = None


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/api/auth/f1-login")
async def f1_login(body: LoginRequest, response: Response):
    email = (body.email or os.environ.get("F1_EMAIL") or "").strip()
    password = body.password or os.environ.get("F1_PASSWORD") or ""
    league_id = body.league_id or DEFAULT_LEAGUE_ID

    if not email or not password:
        raise HTTPException(
            400,
            "Email and password are required (or set F1_EMAIL / F1_PASSWORD in .env).",
        )

    try:
        guid, token = await asyncio.wait_for(
            asyncio.to_thread(f1_login_sync, email, password),
            timeout=180,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, "Login timed out after 3 minutes. Try again.")
    except F1AuthError as exc:
        raise HTTPException(401, str(exc))
    except Exception as exc:
        logger.exception("Unexpected error during F1 login")
        raise HTTPException(500, f"Login failed: {exc}")

    exp = token_expiry(token) or (time.time() + 4 * 86400)
    user_id = upsert_user(guid, email.split("@")[0], token, exp)
    upsert_user_league(user_id, league_id)

    _set_session(response, user_id)

    asyncio.create_task(
        collect_league_data(guid, token, league_id)
    )

    return {
        "user_id": user_id,
        "f1_username": email.split("@")[0],
        "league_id": league_id,
        "token_expires_at": exp,
    }


@app.get("/api/auth/me")
async def auth_me(request: Request):
    user = _require_session(request)
    leagues = get_user_leagues(user["id"])
    return {
        "user_id": user["id"],
        "f1_username": user["f1_username"],
        "f1_guid": user["f1_guid"],
        "leagues": leagues,
        "token_valid": user.get("token_expires_at", 0) > time.time(),
    }


@app.post("/api/auth/logout")
async def auth_logout(response: Response):
    response.delete_cookie(
        SESSION_COOKIE,
        samesite=_COOKIE_SAMESITE,
        secure=IS_PROD,
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# League data endpoints
# ---------------------------------------------------------------------------

@app.get("/api/league/{league_id}/standings")
async def league_standings(league_id: int, request: Request):
    _require_session(request)
    race_data = get_race_results(league_id)
    if not race_data:
        return {"standings": [], "final_race": 0, "race_names": RACE_NAMES}

    budget_data = get_budget_history(league_id)
    members = get_league_members(league_id)
    num_teams: dict[str, int] = {}
    for m in members:
        num_teams[m["user_name"]] = num_teams.get(m["user_name"], 0) + 1

    user_cum, user_per = _build_user_data(race_data)
    final_race = max(race_data.keys())

    standings = []
    sorted_users = sorted(user_cum.items(), key=lambda x: x[1].get(final_race, 0), reverse=True)
    leader_pts = sorted_users[0][1].get(final_race, 0) if sorted_users else 0

    for rank, (name, hist) in enumerate(sorted_users, 1):
        pts = hist.get(final_race, 0)
        last = user_per.get(name, {}).get(final_race, 0)
        races = len([v for v in hist.values() if v > 0])
        avg = pts / races if races else 0
        bh = budget_data.get(name, {})
        valid = [r for r in bh if bh[r].get("max_team_bal", 0) > 0]
        tv = bh[max(valid)]["max_team_bal"] if valid else 0
        start = 100 * num_teams.get(name, 2)
        gain = tv - start if tv else 0
        avg_tv = (start + tv) / 2 if tv else start
        ppm = pts / avg_tv if avg_tv > 0 else 0
        roi = (gain / start * 100) if start else 0

        standings.append({
            "rank": rank, "user_name": name, "total_points": pts,
            "last_race_points": last, "avg_per_race": round(avg, 1),
            "team_value": tv, "budget_gain": gain,
            "points_per_million": round(ppm, 2), "roi_percent": round(roi, 1),
            "gap": round(leader_pts - pts, 1),
        })

    return {
        "standings": standings,
        "final_race": final_race,
        "race_names": RACE_NAMES,
        "total_players": len(standings),
    }


@app.get("/api/league/{league_id}/races")
async def league_races(league_id: int, request: Request):
    _require_session(request)
    race_data = get_race_results(league_id)
    user_cum, user_per = _build_user_data(race_data)
    final_race = max(race_data.keys()) if race_data else 0

    sorted_users = sorted(user_cum.items(), key=lambda x: x[1].get(final_race, 0), reverse=True)

    cumulative = {name: hist for name, hist in sorted_users}
    per_race = {name: user_per.get(name, {}) for name, _ in sorted_users}

    winners = {}
    for rd, entries in race_data.items():
        by_user: dict[str, float] = defaultdict(float)
        for e in entries:
            by_user[e["user_name"]] += e["points"]
        if by_user:
            w = max(by_user.items(), key=lambda x: x[1])
            winners[rd] = {"user_name": w[0], "points": w[1]}

    return {
        "cumulative": cumulative,
        "per_race": per_race,
        "winners": winners,
        "race_names": RACE_NAMES,
        "final_race": final_race,
    }


@app.get("/api/league/{league_id}/budget")
async def league_budget(league_id: int, request: Request):
    _require_session(request)
    budget = get_budget_history(league_id)
    return {"budget": budget, "race_names": RACE_NAMES}


@app.get("/api/league/{league_id}/chips")
async def league_chips(league_id: int, request: Request):
    _require_session(request)
    chips = get_chip_usage(league_id)
    return {"chips": chips, "race_names": RACE_NAMES}


@app.get("/api/league/{league_id}/members")
async def league_members(league_id: int, request: Request):
    _require_session(request)
    members = get_league_members(league_id)
    return {"members": members}


@app.get("/api/schedule")
async def schedule(tz: str = "America/New_York"):
    try:
        user_tz = pytz.timezone(tz)
    except pytz.UnknownTimeZoneError:
        user_tz = pytz.timezone("America/New_York")

    now = datetime.now(pytz.UTC)
    result = []
    next_race = None

    for race in F1_SCHEDULE:
        race_dt_utc = pytz.UTC.localize(
            datetime.strptime(f"{race['date']} {race['time']}", "%Y-%m-%d %H:%M")
        )
        race_dt_local = race_dt_utc.astimezone(user_tz)

        if race_dt_utc < now:
            status = "completed"
        elif next_race is None:
            status = "next"
            next_race = race
        else:
            status = "upcoming"

        result.append({
            "round": race["round"],
            "name": race["name"],
            "location": race["location"],
            "sprint": race.get("sprint", False),
            "date_local": race_dt_local.strftime("%a, %b %d"),
            "time_local": race_dt_local.strftime("%I:%M %p"),
            "date_utc": race["date"],
            "time_utc": race["time"],
            "status": status,
        })

    countdown = None
    if next_race:
        ndt = pytz.UTC.localize(
            datetime.strptime(f"{next_race['date']} {next_race['time']}", "%Y-%m-%d %H:%M")
        )
        delta = ndt - now
        countdown = {
            "name": next_race["name"],
            "days": delta.days,
            "hours": delta.seconds // 3600,
            "date_local": ndt.astimezone(user_tz).strftime("%b %d, %I:%M %p"),
        }

    return {"schedule": result, "next_race": countdown}


@app.post("/api/admin/refresh-all")
async def refresh_all():
    users = get_users_with_valid_tokens()
    results = []
    for u in users:
        leagues = get_user_leagues(u["id"])
        for lg in leagues:
            res = await collect_league_data(u["f1_guid"], u["f1_token"], lg["league_id"])
            results.append(res)
    return {"refreshed": len(results), "details": results}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_user_data(race_data: dict[int, list[dict]]) -> tuple[dict, dict]:
    user_cum: dict[str, dict[int, float]] = {}
    user_per: dict[str, dict[int, float]] = {}
    totals: dict[str, float] = defaultdict(float)
    for rd in sorted(race_data.keys()):
        race_pts: dict[str, float] = defaultdict(float)
        for e in race_data[rd]:
            race_pts[e["user_name"]] += e["points"] or 0
        for name, pts in race_pts.items():
            user_cum.setdefault(name, {})
            user_per.setdefault(name, {})
            totals[name] += pts
            user_cum[name][rd] = totals[name]
            user_per[name][rd] = pts
    return user_cum, user_per
