"""
F1 Fantasy API client.

Extracted from the original app.py. Handles all communication with
fantasy.formula1.com using a user's F1_FANTASY_007 JWT.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from urllib.parse import unquote

import httpx

BASE_URL = "https://fantasy.formula1.com"

CHIP_FIELDS = [
    ("iswildcardtaken",   "wildcardtakengd",   "Wildcard"),
    ("islimitlesstaken",  "limitlesstakengd",   "Limitless"),
    ("isfinalfixtaken",   "finalfixtakengd",    "Final Fix"),
    ("isautopilottaken",  "autopilottakengd",   "Autopilot"),
    ("isnonigativetaken", "nonigativetakengd",  "No Negative"),
    ("isextradrstaken",   "extradrstakengd",    "Extra DRS"),
]


def _f1_data_value(data: dict | None) -> dict | None:
    if not isinstance(data, dict):
        return None
    d = data.get("Data")
    if not isinstance(d, dict):
        return None
    v = d.get("Value")
    return v if isinstance(v, dict) else None


class F1FantasyAPI:
    def __init__(self, user_guid: str, token: str):
        self.user_guid = user_guid
        self.token = token

    def _cookies(self) -> dict[str, str]:
        return {"F1_FANTASY_007": self.token}

    # ------------------------------------------------------------------
    # League members
    # ------------------------------------------------------------------

    async def get_league_members(self, league_id: int) -> dict[str, list[dict]]:
        url = f"/services/user/leaderboard/{self.user_guid}/pvtleagueuserrankget/1/{league_id}/0/1/1/100/"
        async with httpx.AsyncClient(base_url=BASE_URL, cookies=self._cookies(), timeout=30) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return {}
            val = _f1_data_value(resp.json())
            members = (val.get("memRank", []) if val else []) or []
            if not isinstance(members, list):
                return {}
            users: dict[str, list[dict]] = {}
            for m in members:
                user_name = m["userName"]
                users.setdefault(user_name, []).append({
                    "guid": m["guid"],
                    "team_no": m["teamNo"],
                    "team_name": unquote(m["teamName"]),
                })
            return users

    async def get_league_members_flat(self, league_id: int) -> list[dict]:
        users = await self.get_league_members(league_id)
        flat: list[dict] = []
        for user_name, teams in users.items():
            for t in teams:
                flat.append({"user_name": user_name, **t})
        return flat

    # ------------------------------------------------------------------
    # Race data
    # ------------------------------------------------------------------

    async def get_all_race_data(self, league_id: int, num_races: int) -> dict[int, list[dict]]:
        all_race_data: dict[int, list[dict]] = {}
        async with httpx.AsyncClient(base_url=BASE_URL, cookies=self._cookies(), timeout=30) as client:
            for race_id in range(1, num_races + 1):
                url = f"/services/user/leaderboard/{self.user_guid}/pvtleagueuserrankget/2/{league_id}/{race_id}/1/1/100/"
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        val = _f1_data_value(resp.json())
                        if val:
                            members = val.get("memRank", []) or []
                            if isinstance(members, list):
                                all_race_data[race_id] = [
                                    {"team_name": unquote(m["teamName"]),
                                     "user_name": m["userName"],
                                     "points": m["ovPoints"] or 0}
                                    for m in members
                                ]
                except Exception:
                    pass

        if not all_race_data or len(all_race_data) <= 1:
            gd = await self._race_data_from_gameday_api(league_id, num_races)
            if gd and len(gd) > len(all_race_data):
                all_race_data = gd

        if not all_race_data:
            all_race_data = await self._fallback_cumulative(league_id)

        return all_race_data

    async def _race_data_from_gameday_api(self, league_id: int, num_races: int) -> dict[int, list[dict]]:
        roster_url = f"/services/user/leaderboard/{self.user_guid}/pvtleagueuserrankget/1/{league_id}/0/1/1/100/"
        async with httpx.AsyncClient(base_url=BASE_URL, cookies=self._cookies(), timeout=120) as client:
            resp = await client.get(roster_url)
            if resp.status_code != 200:
                return {}
            val = _f1_data_value(resp.json())
            if not val:
                return {}
            members = val.get("memRank", []) or []
            if not isinstance(members, list) or not members:
                return {}

            sem = asyncio.Semaphore(25)

            async def fetch_cell(race_id: int, m: dict) -> dict | None:
                async with sem:
                    url = (f"/services/user/opponentteam/opponentgamedayplayerteamget"
                           f"/1/{m['guid']}/{m['teamNo']}/{race_id}/1")
                    try:
                        rr = await client.get(url)
                        if rr.status_code != 200:
                            return None
                        v = _f1_data_value(rr.json())
                        if not v or not v.get("userTeam"):
                            return None
                        t = v["userTeam"][0]
                        return {
                            "race_id": race_id,
                            "team_name": unquote(m["teamName"]),
                            "user_name": m["userName"],
                            "points": float(t.get("gdpoints") or 0),
                        }
                    except Exception:
                        return None

            tasks = [fetch_cell(rid, m) for rid in range(1, num_races + 1) for m in members]
            results = await asyncio.gather(*tasks)

        by_race: dict[int, list[dict]] = defaultdict(list)
        for row in results:
            if not row:
                continue
            rid = row.pop("race_id")
            by_race[rid].append(row)
        return dict(by_race) if by_race else {}

    async def _fallback_cumulative(self, league_id: int) -> dict[int, list[dict]]:
        url = f"/services/user/leaderboard/{self.user_guid}/pvtleagueuserrankget/1/{league_id}/0/1/1/100/"
        async with httpx.AsyncClient(base_url=BASE_URL, cookies=self._cookies(), timeout=30) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return {}
            val = _f1_data_value(resp.json())
            if not val:
                return {}
            members = val.get("memRank", []) or []
            if not isinstance(members, list):
                return {}
            return {1: [
                {"team_name": unquote(m["teamName"]),
                 "user_name": m["userName"],
                 "points": m.get("ovPoints") or 0}
                for m in members
            ]}

    # ------------------------------------------------------------------
    # Budget data
    # ------------------------------------------------------------------

    async def get_all_budget_data(self, users: dict[str, list[dict]], num_races: int) -> dict[str, dict[int, dict]]:
        all_budget: dict[str, dict[int, dict]] = {}
        async with httpx.AsyncClient(base_url=BASE_URL, cookies=self._cookies(), timeout=30) as client:
            for user_name, teams in users.items():
                user_hist: dict[int, dict] = {}
                for race_id in range(1, num_races + 1):
                    tv = tb = mb = 0.0
                    has_data = False
                    for team in teams:
                        url = (f"/services/user/opponentteam/opponentgamedayplayerteamget"
                               f"/1/{team['guid']}/{team['team_no']}/{race_id}/1")
                        try:
                            resp = await client.get(url)
                            if resp.status_code != 200:
                                continue
                            val = _f1_data_value(resp.json())
                            if not val or not val.get("userTeam"):
                                continue
                            t = val["userTeam"][0]
                            _tv = t.get("teamval") or 0
                            _tb = t.get("teambal") or 0
                            _mb = t.get("maxteambal") or 0
                            info = t.get("team_info") or {}
                            if _tv == 0 and info:
                                _tv = info.get("teamVal") or 0
                            if _tb == 0 and info:
                                _tb = info.get("teamBal") or 0
                            if _mb == 0 and info:
                                _mb = info.get("maxTeambal") or 0
                            if _tv > 0 or _mb > 0:
                                tv += _tv; tb += _tb; mb += _mb
                                has_data = True
                        except Exception:
                            pass
                    if has_data:
                        user_hist[race_id] = {"team_val": tv, "team_bal": tb, "max_team_bal": mb}
                if user_hist:
                    all_budget[user_name] = user_hist
        return all_budget

    # ------------------------------------------------------------------
    # Chip usage
    # ------------------------------------------------------------------

    async def get_all_chip_usage(self, users: dict[str, list[dict]], num_races: int) -> dict[str, list[dict]]:
        all_chips: dict[str, list[dict]] = {}
        async with httpx.AsyncClient(base_url=BASE_URL, cookies=self._cookies(), timeout=30) as client:
            for user_name, teams in users.items():
                user_chips: list[dict] = []
                seen: set[tuple] = set()
                for team_info in teams:
                    for race_id in range(1, num_races + 1):
                        url = (f"/services/user/opponentteam/opponentgamedayplayerteamget"
                               f"/1/{team_info['guid']}/{team_info['team_no']}/{race_id}/1")
                        try:
                            resp = await client.get(url)
                            if resp.status_code != 200:
                                continue
                            val = _f1_data_value(resp.json())
                            ut = (val.get("userTeam") if val else None) or []
                            team = ut[0] if ut else {}
                            for _flag, gd_field, chip_name in CHIP_FIELDS:
                                gd_val = team.get(gd_field)
                                if gd_val is not None and int(gd_val) == race_id:
                                    key = (team_info["team_name"], race_id, chip_name)
                                    if key not in seen:
                                        seen.add(key)
                                        user_chips.append({
                                            "team": team_info["team_name"],
                                            "race": race_id, "chip": chip_name,
                                        })
                        except Exception:
                            pass
                if user_chips:
                    all_chips[user_name] = user_chips
        return all_chips
