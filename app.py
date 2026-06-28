"""
F1 Fantasy Dashboard - DRS Mafia
Streamlit dashboard for tracking league performance, budgets, and efficiency.
"""

import os
import asyncio
from pathlib import Path
from urllib.parse import unquote
from collections import defaultdict
from datetime import datetime
import pytz

import streamlit as st

from f1_playwright_login import F1LoginError, capture_session_via_f1_browser
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import httpx
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# 2026 F1 Calendar (UTC race start times)
# Source: formula1.com/en/racing/2026 & FIA confirmed start times
# Bahrain and Saudi Arabia removed (cancelled).
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

TIMEZONES = [
    "America/Los_Angeles",
    "America/Denver",
    "America/Chicago",
    "America/New_York",
    "America/Toronto",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Singapore",
    "Asia/Tokyo",
    "Australia/Sydney",
    "Pacific/Auckland",
]

_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

LEAGUE_ID = 10328108
LEAGUE_NAME = "The Masala Grid"
NUM_RACES = len(F1_SCHEDULE)

# ---------------------------------------------------------------------------
# Page config & styling
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title=f"F1 Fantasy | {LEAGUE_NAME}",
    page_icon=":material/sports_motorsports:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

_F1_RED = "#e10600"

st.markdown(f"""
<style>
    /* Metric cards */
    [data-testid="stMetric"] {{
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        padding: 16px 20px;
        border-radius: 8px;
        border-left: 3px solid {_F1_RED};
    }}
    [data-testid="stMetricLabel"] {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }}
    [data-testid="stMetricValue"] {{ font-weight: 700; }}

    /* Headings */
    h1 {{ color: #ffffff !important; font-weight: 800 !important; }}
    h2, h3 {{ color: #e0e0e0 !important; font-weight: 600 !important; }}

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
    .stTabs [data-baseweb="tab"] {{
        background-color: #16213e;
        border-radius: 6px 6px 0 0;
        padding: 8px 20px;
        font-weight: 500;
    }}
    .stTabs [aria-selected="true"] {{
        border-bottom: 2px solid {_F1_RED} !important;
    }}

    /* Subtle divider */
    hr {{ border-color: #2a2a4a !important; }}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Chip detection fields
# ---------------------------------------------------------------------------
_CHIP_FIELDS = [
    ("iswildcardtaken",   "wildcardtakengd",   "Wildcard"),
    ("islimitlesstaken",  "limitlesstakengd",   "Limitless"),
    ("isfinalfixtaken",   "finalfixtakengd",    "Final Fix"),
    ("isautopilottaken",  "autopilottakengd",   "Autopilot"),
    ("isnonigativetaken", "nonigativetakengd",  "No Negative"),
    ("isextradrstaken",   "extradrstakengd",    "Extra DRS"),
]


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _f1_data_value(data: dict | None) -> dict | None:
    if not isinstance(data, dict):
        return None
    d = data.get("Data")
    if not isinstance(d, dict):
        return None
    v = d.get("Value")
    return v if isinstance(v, dict) else None


class F1FantasyAPI:
    def __init__(self, user_guid: str | None = None, token: str | None = None):
        self.user_guid = (user_guid or os.environ.get("F1_USER_GUID") or "").strip() or None
        self.token = (token or os.environ.get("F1_TOKEN") or "").strip() or None
        self.base_url = "https://fantasy.formula1.com"

    async def get_league_members(self, league_id: int) -> dict:
        url = f"/services/user/leaderboard/{self.user_guid}/pvtleagueuserrankget/1/{league_id}/0/1/1/100/"
        async with httpx.AsyncClient(base_url=self.base_url, cookies={"F1_FANTASY_007": self.token}) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                val = _f1_data_value(data)
                members = (val.get("memRank", []) if val else []) or []
                if not isinstance(members, list):
                    members = []
                users: dict = {}
                for m in members:
                    user_name = m["userName"]
                    if user_name not in users:
                        users[user_name] = []
                    users[user_name].append({
                        "guid": m["guid"],
                        "team_no": m["teamNo"],
                        "team_name": unquote(m["teamName"]),
                    })
                return users
        return {}

    async def diagnose_empty_race_data(self, league_id: int) -> str:
        if not self.user_guid or not self.token:
            return "No F1 session loaded. Sign in with your F1 email and password."
        url = f"/services/user/leaderboard/{self.user_guid}/pvtleagueuserrankget/2/{league_id}/1/1/1/100/"
        async with httpx.AsyncClient(base_url=self.base_url, cookies={"F1_FANTASY_007": self.token}, timeout=30.0) as client:
            try:
                resp = await client.get(url)
            except httpx.RequestError as exc:
                return f"Network error: {exc!s}"
        if resp.status_code in (401, 403):
            return f"HTTP {resp.status_code} - session expired or invalid. Sign in again."
        if resp.status_code != 200:
            return f"HTTP {resp.status_code} from the leaderboard API. Check LEAGUE_ID or sign in again."
        try:
            data = resp.json()
        except Exception:
            return "The API returned 200 but the body was not JSON."
        if not _f1_data_value(data):
            return "Session works but round 1 returned no data. LEAGUE_ID may not match your private league."
        return "Unexpected empty dataset. Try clearing cache and reloading."

    async def get_all_race_data(self, league_id: int, num_races: int) -> tuple[dict, str]:
        all_race_data: dict = {}
        source = "type2"
        async with httpx.AsyncClient(base_url=self.base_url, cookies={"F1_FANTASY_007": self.token}, timeout=30.0) as client:
            for race_id in range(1, num_races + 1):
                url = f"/services/user/leaderboard/{self.user_guid}/pvtleagueuserrankget/2/{league_id}/{race_id}/1/1/100/"
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        val = _f1_data_value(data)
                        if val:
                            members = val.get("memRank", []) or []
                            if not isinstance(members, list):
                                members = []
                            all_race_data[race_id] = [
                                {"team_name": unquote(m["teamName"]), "user_name": m["userName"], "points": m["ovPoints"] or 0}
                                for m in members
                            ]
                except Exception:
                    pass

        if not all_race_data:
            all_race_data = await self._race_data_from_gameday_api(league_id, num_races)
            if all_race_data:
                source = "gameday"
        elif len(all_race_data) == 1:
            gd = await self._race_data_from_gameday_api(league_id, num_races)
            if gd and len(gd) > 1:
                all_race_data = gd
                source = "gameday"

        if not all_race_data:
            all_race_data = await self._fallback_cumulative_from_roster(league_id)
            if all_race_data:
                source = "roster"

        return all_race_data, source

    async def _race_data_from_gameday_api(self, league_id: int, num_races: int) -> dict:
        roster_url = f"/services/user/leaderboard/{self.user_guid}/pvtleagueuserrankget/1/{league_id}/0/1/1/100/"
        async with httpx.AsyncClient(base_url=self.base_url, cookies={"F1_FANTASY_007": self.token}, timeout=120.0) as client:
            resp = await client.get(roster_url)
            if resp.status_code != 200:
                return {}
            try:
                data = resp.json()
            except Exception:
                return {}
            val = _f1_data_value(data)
            if not val:
                return {}
            members = val.get("memRank", []) or []
            if not isinstance(members, list) or not members:
                return {}

            sem = asyncio.Semaphore(25)

            async def fetch_cell(race_id: int, m: dict) -> dict | None:
                async with sem:
                    url = f"/services/user/opponentteam/opponentgamedayplayerteamget/1/{m['guid']}/{m['teamNo']}/{race_id}/1"
                    try:
                        rr = await client.get(url)
                        if rr.status_code != 200:
                            return None
                        jd = rr.json()
                        v = _f1_data_value(jd)
                        if not v or not v.get("userTeam"):
                            return None
                        t = v["userTeam"][0]
                        return {"race_id": race_id, "team_name": unquote(m["teamName"]), "user_name": m["userName"], "points": float(t.get("gdpoints") or 0)}
                    except Exception:
                        return None

            tasks = [fetch_cell(rid, m) for rid in range(1, num_races + 1) for m in members]
            results = await asyncio.gather(*tasks)

        by_race: dict[int, list] = defaultdict(list)
        for row in results:
            if not row:
                continue
            rid = row.pop("race_id")
            by_race[rid].append(row)
        return dict(by_race) if by_race else {}

    async def _fallback_cumulative_from_roster(self, league_id: int) -> dict:
        url = f"/services/user/leaderboard/{self.user_guid}/pvtleagueuserrankget/1/{league_id}/0/1/1/100/"
        async with httpx.AsyncClient(base_url=self.base_url, cookies={"F1_FANTASY_007": self.token}, timeout=30.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return {}
            try:
                data = resp.json()
            except Exception:
                return {}
            val = _f1_data_value(data)
            if not val:
                return {}
            members = val.get("memRank", []) or []
            if not isinstance(members, list):
                return {}
            return {1: [{"team_name": unquote(m["teamName"]), "user_name": m["userName"], "points": m.get("ovPoints") or 0} for m in members]}

    async def get_all_budget_data(self, users: dict, num_races: int) -> dict:
        all_budget_data: dict = {}
        async with httpx.AsyncClient(base_url=self.base_url, cookies={"F1_FANTASY_007": self.token}, timeout=30.0) as client:
            for user_name, teams in users.items():
                user_budget_history: dict = {}
                for race_id in range(1, num_races + 1):
                    race_total_val = race_total_bal = race_max_bal = 0
                    has_data = False
                    for team in teams:
                        url = f"{self.base_url}/services/user/opponentteam/opponentgamedayplayerteamget/1/{team['guid']}/{team['team_no']}/{race_id}/1"
                        try:
                            resp = await client.get(url)
                            if resp.status_code == 200:
                                data = resp.json()
                                val = _f1_data_value(data)
                                if val and val.get("userTeam"):
                                    t = val["userTeam"][0]
                                    tv = t.get("teamval") or 0
                                    tb = t.get("teambal") or 0
                                    mb = t.get("maxteambal") or 0
                                    team_info = t.get("team_info", {})
                                    if tv == 0 and team_info:
                                        tv = team_info.get("teamVal") or 0
                                    if tb == 0 and team_info:
                                        tb = team_info.get("teamBal") or 0
                                    if mb == 0 and team_info:
                                        mb = team_info.get("maxTeambal") or 0
                                    if tv > 0 or mb > 0:
                                        race_total_val += tv
                                        race_total_bal += tb
                                        race_max_bal += mb
                                        has_data = True
                        except Exception:
                            pass
                    if has_data:
                        user_budget_history[race_id] = {"team_val": race_total_val, "team_bal": race_total_bal, "max_team_bal": race_max_bal}
                if user_budget_history:
                    all_budget_data[user_name] = user_budget_history
        return all_budget_data

    async def get_all_chip_usage(self, users: dict, num_races: int) -> dict:
        all_chips: dict[str, list[dict]] = {}
        async with httpx.AsyncClient(base_url=self.base_url, cookies={"F1_FANTASY_007": self.token}, timeout=30.0) as client:
            for user_name, teams in users.items():
                user_chips: list[dict] = []
                seen: set[tuple] = set()
                for team_info in teams:
                    for race_id in range(1, num_races + 1):
                        url = f"/services/user/opponentteam/opponentgamedayplayerteamget/1/{team_info['guid']}/{team_info['team_no']}/{race_id}/1"
                        try:
                            resp = await client.get(url)
                            if resp.status_code != 200:
                                continue
                            data = resp.json()
                            val = _f1_data_value(data)
                            ut = (val.get("userTeam") if val else None) or []
                            team = ut[0] if ut else {}
                            for _flag, gd_field, chip_name in _CHIP_FIELDS:
                                gd_val = team.get(gd_field)
                                if gd_val is not None and int(gd_val) == race_id:
                                    key = (team_info["team_name"], race_id, chip_name)
                                    if key not in seen:
                                        seen.add(key)
                                        user_chips.append({"team": team_info["team_name"], "race": race_id, "chip": chip_name})
                        except Exception:
                            pass
                if user_chips:
                    all_chips[user_name] = user_chips
        return all_chips


# ---------------------------------------------------------------------------
# Data processing
# ---------------------------------------------------------------------------

def build_user_data(all_race_data: dict) -> tuple:
    user_cumulative: dict = {}
    user_per_race: dict = {}
    cumulative_totals: dict = defaultdict(float)
    for race_id in sorted(all_race_data.keys()):
        race_points: dict = defaultdict(float)
        for entry in all_race_data[race_id]:
            race_points[entry["user_name"]] += entry["points"] or 0
        for user_name, points in race_points.items():
            if user_name not in user_cumulative:
                user_cumulative[user_name] = {}
                user_per_race[user_name] = {}
            cumulative_totals[user_name] += points
            user_cumulative[user_name][race_id] = cumulative_totals[user_name]
            user_per_race[user_name][race_id] = points
    return user_cumulative, user_per_race


def calculate_metrics(user_cumulative: dict, budget_data: dict, num_teams_per_user: dict) -> dict:
    metrics: dict = {}
    for user_name, history in user_cumulative.items():
        if not history:
            continue
        final_race = max(history.keys())
        total_points = history.get(final_race, 0) or 0
        budget_history = budget_data.get(user_name, {})
        if budget_history:
            valid_races = [r for r in budget_history.keys() if budget_history[r]["max_team_bal"] > 0]
            if valid_races:
                final_team_val = budget_history[max(valid_races)]["max_team_bal"]
                starting_budget = 100 * num_teams_per_user.get(user_name, 2)
            else:
                final_team_val = starting_budget = 0
        else:
            final_team_val = starting_budget = 0
        budget_gain = final_team_val - starting_budget if starting_budget > 0 else 0
        avg_team_val = (starting_budget + final_team_val) / 2 if final_team_val > 0 else starting_budget
        points_per_million = total_points / avg_team_val if avg_team_val > 0 else 0
        roi = (budget_gain / starting_budget * 100) if starting_budget > 0 else 0
        metrics[user_name] = {
            "total_points": total_points,
            "final_team_val": final_team_val,
            "starting_budget": starting_budget,
            "budget_gain": budget_gain,
            "points_per_million": points_per_million,
            "roi_percent": roi,
        }
    return metrics


def get_race_names():
    return {r["round"]: r["name"] for r in F1_SCHEDULE}


def race_utc(race: dict) -> datetime:
    return pytz.UTC.localize(datetime.strptime(f"{race['date']} {race['time']}", "%Y-%m-%d %H:%M"))


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def _trim_trailing_unplayed_races(all_race_data: dict) -> dict:
    if not all_race_data:
        return all_race_data
    ids = sorted(all_race_data.keys())
    last_played = None
    for rid in reversed(ids):
        rows = all_race_data.get(rid) or []
        if not rows:
            continue
        mx = max((float(r.get("points") or 0) for r in rows), default=0.0)
        if mx > 0:
            last_played = rid
            break
    if last_played is None:
        return all_race_data
    return {rid: all_race_data[rid] for rid in ids if rid <= last_played}


def _completed_rounds_from_calendar() -> set[int] | None:
    now = datetime.now(pytz.UTC)
    completed: set[int] = set()
    for race in F1_SCHEDULE:
        if race_utc(race) < now:
            completed.add(race["round"])
    return completed if completed else None


def filter_race_data_to_completed_rounds(all_race_data: dict) -> dict:
    trimmed = _trim_trailing_unplayed_races(all_race_data)
    if not trimmed:
        return trimmed
    cal = _completed_rounds_from_calendar()
    if not cal:
        return trimmed
    max_cal = max(cal)
    max_data = max(trimmed.keys())
    if max_data > max_cal:
        return trimmed
    capped = {rid: v for rid, v in trimmed.items() if rid in cal}
    return capped if capped else trimmed


def filter_chip_data_by_max_race(chip_data: dict, max_race: int) -> dict:
    if not chip_data or max_race < 1:
        return chip_data
    return {u: [c for c in chips if c.get("race", 0) <= max_race] for u, chips in chip_data.items() if any(c.get("race", 0) <= max_race for c in chips)}


def filter_budget_data_by_max_race(budget_data: dict, max_race: int) -> dict:
    if not budget_data or max_race < 1:
        return budget_data
    out: dict = {}
    for u, hist in budget_data.items():
        sub = {rid: v for rid, v in hist.items() if rid <= max_race}
        if sub:
            out[u] = sub
    return out


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def fetch_data(user_guid: str, token: str):
    api = F1FantasyAPI(user_guid=user_guid, token=token)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    all_race_data, race_source = loop.run_until_complete(api.get_all_race_data(LEAGUE_ID, NUM_RACES))
    users = loop.run_until_complete(api.get_league_members(LEAGUE_ID))
    chip_data = loop.run_until_complete(api.get_all_chip_usage(users, NUM_RACES))
    budget_data = loop.run_until_complete(api.get_all_budget_data(users, NUM_RACES))
    error_detail = None
    if not all_race_data:
        error_detail = loop.run_until_complete(api.diagnose_empty_race_data(LEAGUE_ID))
    loop.close()
    if all_race_data:
        all_race_data = filter_race_data_to_completed_rounds(all_race_data)
        max_r = max(all_race_data.keys())
        chip_data = filter_chip_data_by_max_race(chip_data, max_r)
        budget_data = filter_budget_data_by_max_race(budget_data, max_r)
    return all_race_data, chip_data, budget_data, users, error_detail, race_source


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _init_f1_session_state():
    if "f1_user_guid" not in st.session_state:
        st.session_state.f1_user_guid = os.environ.get("F1_USER_GUID") or ""
    if "f1_token" not in st.session_state:
        st.session_state.f1_token = os.environ.get("F1_TOKEN") or ""


@st.dialog("Sign in to F1 Fantasy")
def f1_login_modal():
    banner = st.session_state.pop("f1_login_error_banner", None)
    if banner:
        st.warning(banner)

    st.markdown(
        "1. Click **Open sign-in window** below.\n\n"
        "2. A browser window opens on **F1 Fantasy**. Cookie consent is auto-accepted "
        "and **Sign In** is clicked for you.\n\n"
        "3. Enter your **F1 email and password** in the login form. "
        "Complete any 2FA/CAPTCHA if prompted.\n\n"
        "4. After login, the site redirects back to Fantasy. "
        "Your session is captured automatically and the window closes."
    )

    if st.button("Open sign-in window", type="primary", key="f1_btn_open_signin", use_container_width=True):
        with st.spinner("Waiting for sign-in to complete..."):
            try:
                g, t = capture_session_via_f1_browser()
            except F1LoginError as e:
                st.session_state.f1_login_error_banner = str(e)
                st.rerun()
            else:
                st.session_state.f1_user_guid = g
                st.session_state.f1_token = t
                fetch_data.clear()
                st.rerun()


# ---------------------------------------------------------------------------
# Plotly defaults
# ---------------------------------------------------------------------------
_PLOT_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, system-ui, sans-serif"),
    margin=dict(l=40, r=20, t=48, b=40),
)


def _race_xaxis(final_race: int, race_names: dict) -> dict:
    return dict(
        tickmode="array",
        tickvals=list(range(1, final_race + 1)),
        ticktext=[race_names.get(i, f"R{i}") for i in range(1, final_race + 1)],
        tickangle=-45,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    _init_f1_session_state()
    guid = (st.session_state.f1_user_guid or "").strip()
    token = (st.session_state.f1_token or "").strip()
    connected = bool(guid and token)

    if connected:
        with st.sidebar:
            st.markdown("### Controls")
            c1, c2 = st.sidebar.columns(2)
            with c1:
                if st.button("Refresh data", key="f1_btn_refresh_data"):
                    fetch_data.clear()
                    st.rerun()
            with c2:
                if st.button("Sign out", key="f1_btn_clear_session"):
                    st.session_state.f1_user_guid = ""
                    st.session_state.f1_token = ""
                    fetch_data.clear()
                    st.rerun()

    if not connected:
        st.title("F1 Fantasy Dashboard")
        st.caption("Sign in to load your league data.")
        f1_login_modal()
        return

    st.title("F1 Fantasy Dashboard")
    st.caption(LEAGUE_NAME)

    with st.spinner("Loading race data..."):
        all_race_data, chip_data, budget_data, users, error_detail, race_source = fetch_data(guid, token)

    if not all_race_data:
        st.session_state.f1_login_error_banner = error_detail or "Could not load race data. Session may be expired."
        st.session_state.f1_user_guid = ""
        st.session_state.f1_token = ""
        fetch_data.clear()
        st.rerun()

    num_teams_per_user = {name: len(teams) for name, teams in users.items()}
    user_cumulative, user_per_race = build_user_data(all_race_data)
    metrics = calculate_metrics(user_cumulative, budget_data, num_teams_per_user)

    final_race = max(all_race_data.keys())
    active_users = {n: d for n, d in user_cumulative.items() if d.get(final_race, 0) > 0}
    if not active_users and user_cumulative:
        active_users = dict(user_cumulative)

    sorted_users = sorted(active_users.items(), key=lambda x: x[1].get(final_race, 0), reverse=True)
    race_names = get_race_names()

    if race_source == "roster":
        st.info("Per-race scores are not available yet. Showing cumulative points from the league roster.")

    if not sorted_users:
        st.warning("No player data to display.")
        return

    # === METRICS ===
    leader_name, leader_data = sorted_users[0]
    leader_points = leader_data.get(final_race, 0)

    your_name = "Nehel Malhotra"
    your_pos = next((i + 1 for i, (name, _) in enumerate(sorted_users) if name == your_name), None)
    your_points = active_users.get(your_name, {}).get(final_race, 0)
    your_metrics = metrics.get(your_name, {})

    cols = st.columns(5)
    with cols[0]:
        st.metric("Leader", leader_name, f"{leader_points:,.0f} pts")
    with cols[1]:
        st.metric("Players", len(sorted_users))
    with cols[2]:
        st.metric("Races Completed", final_race)
    with cols[3]:
        if your_pos:
            gap = leader_points - your_points
            st.metric("Your Position", f"#{your_pos}", f"-{gap:,.0f} pts" if gap > 0 else "Leading")
    with cols[4]:
        if your_metrics:
            st.metric("Your Team Value", f"${your_metrics.get('final_team_val', 0):,.1f}M",
                      f"+${your_metrics.get('budget_gain', 0):,.1f}M")

    st.divider()

    # === TABS ===
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "Points", "Budget", "Efficiency", "Standings", "Race Breakdown", "Chip Usage", "Schedule"
    ])

    # --- TAB 1: POINTS ---
    with tab1:
        st.subheader("Cumulative Points")
        chart_data = []
        for user_name, history in sorted_users:
            for race_id, points in history.items():
                chart_data.append({"User": user_name, "Race": race_id, "Race Name": race_names.get(race_id, f"R{race_id}"), "Points": points})
        df = pd.DataFrame(chart_data)
        fig = px.line(df, x="Race", y="Points", color="User", markers=True, hover_data=["Race Name"])
        fig.update_layout(**_PLOT_LAYOUT, height=560, xaxis_title="Race Weekend", yaxis_title="Cumulative Points",
                          legend=dict(yanchor="top", y=0.99, xanchor="left", x=1.02), hovermode="x unified")
        fig.update_xaxes(**_race_xaxis(final_race, race_names))
        st.plotly_chart(fig, use_container_width=True)

    # --- TAB 2: BUDGET ---
    with tab2:
        st.subheader("Team Value Evolution")
        if budget_data:
            sorted_budget_users = sorted(budget_data.items(), key=lambda x: max([v["max_team_bal"] for v in x[1].values()] or [0]), reverse=True)
            budget_chart_data = []
            for user_name, history in sorted_budget_users:
                for race_id, data in history.items():
                    if data["max_team_bal"] > 0:
                        budget_chart_data.append({"User": user_name, "Race": race_id, "Race Name": race_names.get(race_id, f"R{race_id}"), "Team Value ($M)": data["max_team_bal"]})
            budget_df = pd.DataFrame(budget_chart_data)
            if not budget_df.empty:
                fig_budget = px.line(budget_df, x="Race", y="Team Value ($M)", color="User", markers=True, hover_data=["Race Name"])
                fig_budget.add_hline(y=200, line_dash="dash", line_color="rgba(255,255,255,0.3)", annotation_text="Starting ($200M)", annotation_position="top left")
                fig_budget.update_layout(**_PLOT_LAYOUT, height=560, xaxis_title="Race Weekend", yaxis_title="Team Value ($M)",
                                         legend=dict(yanchor="top", y=0.99, xanchor="left", x=1.02), hovermode="x unified")
                fig_budget.update_xaxes(**_race_xaxis(final_race, race_names))
                st.plotly_chart(fig_budget, use_container_width=True)

                st.subheader("Value Summary")
                budget_summary = []
                for user_name, history in sorted_budget_users:
                    valid_vals = [v["max_team_bal"] for v in history.values() if v["max_team_bal"] > 0]
                    if valid_vals:
                        final_val = valid_vals[-1]
                        gain = final_val - 200
                        budget_summary.append({"User": user_name, "Final Value": f"${final_val:,.1f}M",
                                               "Gain": f"+${gain:,.1f}M" if gain >= 0 else f"-${abs(gain):,.1f}M",
                                               "ROI": f"{(gain / 200) * 100:+.1f}%"})
                st.dataframe(pd.DataFrame(budget_summary), use_container_width=True, hide_index=True)
        else:
            st.info("Budget data not available.")

    # --- TAB 3: EFFICIENCY ---
    with tab3:
        st.subheader("Efficiency Analysis")
        if metrics:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### Points per $M Invested")
                eff_data = sorted([(n, m["points_per_million"]) for n, m in metrics.items() if m["points_per_million"] > 0], key=lambda x: x[1], reverse=True)
                eff_df = pd.DataFrame(eff_data, columns=["User", "Points/$M"])
                fig_eff = px.bar(eff_df, x="Points/$M", y="User", orientation="h", color="Points/$M", color_continuous_scale="Viridis")
                fig_eff.update_layout(**_PLOT_LAYOUT, height=400, yaxis={"categoryorder": "total ascending"}, showlegend=False, coloraxis_showscale=False)
                st.plotly_chart(fig_eff, use_container_width=True)
            with col2:
                st.markdown("#### ROI % (Team Value Growth)")
                roi_data = sorted([(n, m["roi_percent"]) for n, m in metrics.items() if m["roi_percent"] != 0], key=lambda x: x[1], reverse=True)
                roi_df = pd.DataFrame(roi_data, columns=["User", "ROI %"])
                fig_roi = px.bar(roi_df, x="ROI %", y="User", orientation="h", color="ROI %", color_continuous_scale="RdYlGn")
                fig_roi.update_layout(**_PLOT_LAYOUT, height=400, yaxis={"categoryorder": "total ascending"}, showlegend=False, coloraxis_showscale=False)
                st.plotly_chart(fig_roi, use_container_width=True)

            st.subheader("Metrics Table")
            metrics_table = []
            for i, (name, _) in enumerate(sorted_users):
                m = metrics.get(name, {})
                if m:
                    metrics_table.append({
                        "#": i + 1, "User": name, "Points": f"{m['total_points']:,.0f}",
                        "Team Value": f"${m['final_team_val']:,.1f}M",
                        "Gain": f"+${m['budget_gain']:,.1f}M" if m["budget_gain"] >= 0 else f"${m['budget_gain']:,.1f}M",
                        "Pts/$M": f"{m['points_per_million']:.1f}", "ROI": f"{m['roi_percent']:+.1f}%"
                    })
            st.dataframe(pd.DataFrame(metrics_table), use_container_width=True, hide_index=True)
        else:
            st.info("Efficiency data not available.")

    # --- TAB 4: STANDINGS ---
    with tab4:
        st.subheader("League Standings")
        standings_data = []
        for i, (user_name, history) in enumerate(sorted_users):
            final_pts = history.get(final_race, 0)
            race_pts = user_per_race.get(user_name, {}).get(final_race, 0)
            races_played = len([r for r in history.values() if r > 0])
            avg_pts = final_pts / races_played if races_played > 0 else 0
            gap = leader_points - final_pts
            m = metrics.get(user_name, {})
            standings_data.append({
                "#": i + 1, "User": user_name, "Total": f"{final_pts:,.0f}", "Last Race": f"{race_pts:,.0f}",
                "Avg/Race": f"{avg_pts:,.0f}", "Value": f"${m.get('final_team_val', 0):,.1f}M" if m else "-",
                "Gap": f"-{gap:,.0f}" if gap > 0 else "Leader"
            })
        st.dataframe(pd.DataFrame(standings_data), use_container_width=True, hide_index=True,
                     column_config={"#": st.column_config.NumberColumn(width="small")})

    # --- TAB 5: RACE BREAKDOWN ---
    with tab5:
        st.subheader("Points per Race Weekend")
        race_data = []
        for user_name in [u[0] for u in sorted_users]:
            per_race = user_per_race.get(user_name, {})
            for race_id, points in per_race.items():
                race_data.append({"User": user_name, "Race": race_id, "Race Name": race_names.get(race_id, f"R{race_id}"), "Points": points})
        race_df = pd.DataFrame(race_data)
        pivot_df = race_df.pivot(index="User", columns="Race", values="Points")
        pivot_df = pivot_df.reindex([u[0] for u in sorted_users])
        pivot_df.columns = [race_names.get(c, f"R{c}") for c in pivot_df.columns]
        fig_heat = px.imshow(pivot_df, labels=dict(x="Race Weekend", y="User", color="Points"), color_continuous_scale="RdYlGn", aspect="auto")
        fig_heat.update_layout(**_PLOT_LAYOUT, height=400, xaxis_tickangle=-45)
        st.plotly_chart(fig_heat, use_container_width=True)

        st.subheader("Race Winners")
        race_winners = []
        for race_id in sorted(all_race_data.keys()):
            race_points: dict = defaultdict(float)
            for entry in all_race_data[race_id]:
                race_points[entry["user_name"]] += entry["points"] or 0
            if race_points:
                winner = max(race_points.items(), key=lambda x: x[1])
                race_winners.append({"Race": race_id, "GP": race_names.get(race_id, f"R{race_id}"), "Winner": winner[0], "Points": f"{winner[1]:,.0f}"})
        winners_df = pd.DataFrame(race_winners)
        win_counts = winners_df["Winner"].value_counts().to_dict()
        col1, col2 = st.columns([2, 1])
        with col1:
            st.dataframe(winners_df, use_container_width=True, hide_index=True)
        with col2:
            st.markdown("**Win Count**")
            for user, wins in sorted(win_counts.items(), key=lambda x: -x[1]):
                st.write(f"{user}: {wins}")

    # --- TAB 6: CHIP USAGE ---
    with tab6:
        st.subheader("Chip Usage")
        if chip_data:
            chip_timeline = []
            for user_name, chips in chip_data.items():
                for chip in chips:
                    chip_timeline.append({"User": user_name, "Team": chip["team"], "Race": chip["race"],
                                          "Race Name": race_names.get(chip["race"], f"R{chip['race']}"), "Chip": chip["chip"]})
            chip_df = pd.DataFrame(chip_timeline)
            if not chip_df.empty:
                all_chip_users = sorted(chip_df["User"].unique())
                race_ids = sorted(chip_df["Race"].unique())

                grid_rows = []
                for user in all_chip_users:
                    row: dict[str, str] = {"Player": user}
                    for rid in race_ids:
                        subset = chip_df[(chip_df["User"] == user) & (chip_df["Race"] == rid)]
                        if subset.empty:
                            row[race_names.get(rid, f"R{rid}")] = ""
                        else:
                            row[race_names.get(rid, f"R{rid}")] = ", ".join(subset["Chip"])
                    grid_rows.append(row)
                st.dataframe(pd.DataFrame(grid_rows), use_container_width=True, hide_index=True)

                st.subheader("Chip Timeline")
                chip_df_plot = chip_df.copy()
                chip_types = chip_df_plot["Chip"].unique().tolist()
                jitter_map = {c: i * 0.15 for i, c in enumerate(chip_types)}
                chip_df_plot["Race_j"] = chip_df_plot.apply(lambda r: r["Race"] + jitter_map.get(r["Chip"], 0), axis=1)
                fig_chips = px.scatter(chip_df_plot, x="Race_j", y="User", color="Chip", symbol="Chip",
                                       hover_data={"Team": True, "Race Name": True, "Race_j": False, "Race": True})
                fig_chips.update_traces(marker=dict(size=14, line=dict(width=1, color="white")))
                fig_chips.update_layout(**_PLOT_LAYOUT, height=max(300, len(all_chip_users) * 50 + 100), xaxis_title="Race Weekend", legend_title_text="Chip")
                fig_chips.update_xaxes(**_race_xaxis(final_race, race_names))
                st.plotly_chart(fig_chips, use_container_width=True)

                st.subheader("Chips Used Per Player")
                chip_counts = chip_df.groupby(["User", "Chip"]).size().unstack(fill_value=0)
                chip_counts["Total"] = chip_counts.sum(axis=1)
                chip_counts = chip_counts.sort_values("Total", ascending=False)
                st.dataframe(chip_counts, use_container_width=True)
        else:
            st.info("No chip usage data yet.")

    # --- TAB 7: SCHEDULE ---
    with tab7:
        st.subheader("2026 Race Calendar")
        col1, col2 = st.columns([1, 3])
        with col1:
            selected_tz = st.selectbox("Timezone", options=TIMEZONES,
                                       index=TIMEZONES.index("America/New_York") if "America/New_York" in TIMEZONES else 0)
        user_tz = pytz.timezone(selected_tz)
        schedule_data = []
        now = datetime.now(pytz.UTC)
        next_race = None
        for race in F1_SCHEDULE:
            race_dt_utc = race_utc(race)
            race_dt_local = race_dt_utc.astimezone(user_tz)
            if race_dt_utc < now:
                status = "Completed"
            elif next_race is None:
                status = "NEXT"
                next_race = race
            else:
                status = "Upcoming"
            sprint_tag = "  [Sprint]" if race.get("sprint") else ""
            schedule_data.append({"#": race["round"], "Grand Prix": f"{race['name']}{sprint_tag}", "Circuit": race["location"],
                                  "Date": race_dt_local.strftime("%a, %b %d"), "Local Time": race_dt_local.strftime("%I:%M %p"), "Status": status})
        st.dataframe(pd.DataFrame(schedule_data), use_container_width=True, hide_index=True,
                     column_config={"#": st.column_config.NumberColumn(width="small"), "Status": st.column_config.TextColumn(width="small")})

        if next_race:
            race_dt_utc = race_utc(next_race)
            race_dt_local = race_dt_utc.astimezone(user_tz)
            time_until = race_dt_utc - now
            st.divider()
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Next Race", next_race["name"])
            with c2:
                st.metric("Date / Time", race_dt_local.strftime("%b %d, %I:%M %p"))
            with c3:
                st.metric("Countdown", f"{time_until.days}d {time_until.seconds // 3600}h")

    st.divider()
    st.caption("Data from F1 Fantasy API")


if __name__ == "__main__":
    main()
