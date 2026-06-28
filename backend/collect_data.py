"""
Data collection: fetches F1 Fantasy league data and stores it in SQLite.

Can be run standalone (CLI) or called from the FastAPI server.
"""

from __future__ import annotations

import asyncio
import logging

from f1_api import F1FantasyAPI
from db import (
    init_db,
    get_collected_rounds,
    get_league_members as db_get_members,
    upsert_league_members,
    upsert_race_results,
    upsert_budget,
    upsert_chip,
)

logger = logging.getLogger(__name__)

NUM_RACES = 22


def _trim_trailing_zeros(data: dict[int, list[dict]]) -> dict[int, list[dict]]:
    if not data:
        return data
    ids = sorted(data.keys())
    last_played = None
    for rid in reversed(ids):
        rows = data.get(rid) or []
        mx = max((float(r.get("points") or 0) for r in rows), default=0.0)
        if mx > 0:
            last_played = rid
            break
    if last_played is None:
        return data
    return {rid: data[rid] for rid in ids if rid <= last_played}


async def collect_league_data(
    user_guid: str,
    token: str,
    league_id: int,
    *,
    force: bool = False,
) -> dict:
    """
    Fetch all race/budget/chip data for a league and persist to SQLite.

    Returns a summary dict with counts of what was collected.
    """
    init_db()
    api = F1FantasyAPI(user_guid, token)

    members_by_user = await api.get_league_members(league_id)
    if not members_by_user:
        return {"error": "Could not fetch league members. Token may be expired."}

    flat_members = []
    for user_name, teams in members_by_user.items():
        for t in teams:
            flat_members.append({"user_name": user_name, **t})
    upsert_league_members(league_id, flat_members)

    already = get_collected_rounds(league_id)

    race_data = await api.get_all_race_data(league_id, NUM_RACES)
    race_data = _trim_trailing_zeros(race_data)

    new_rounds = 0
    for race_round, entries in race_data.items():
        if not force and race_round in already:
            continue
        upsert_race_results(league_id, race_round, entries)
        new_rounds += 1

    budget_data = await api.get_all_budget_data(members_by_user, NUM_RACES)
    budget_count = 0
    for user_name, hist in budget_data.items():
        for race_round, vals in hist.items():
            if vals.get("max_team_bal", 0) > 0:
                upsert_budget(league_id, race_round, user_name,
                              vals["team_val"], vals["team_bal"], vals["max_team_bal"])
                budget_count += 1

    chip_data = await api.get_all_chip_usage(members_by_user, NUM_RACES)
    chip_count = 0
    for user_name, chips in chip_data.items():
        for c in chips:
            upsert_chip(league_id, c["race"], user_name, c["team"], c["chip"])
            chip_count += 1

    return {
        "league_id": league_id,
        "members": len(flat_members),
        "new_race_rounds": new_rounds,
        "total_race_rounds": len(race_data),
        "budget_entries": budget_count,
        "chip_entries": chip_count,
    }


def collect_sync(user_guid: str, token: str, league_id: int, *, force: bool = False) -> dict:
    return asyncio.run(collect_league_data(user_guid, token, league_id, force=force))


if __name__ == "__main__":
    import argparse
    import os
    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser(description="Collect F1 Fantasy league data")
    parser.add_argument("--league", type=int, default=10328108)
    parser.add_argument("--guid", default=os.environ.get("F1_USER_GUID"))
    parser.add_argument("--token", default=os.environ.get("F1_TOKEN"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.guid or not args.token:
        print("Set F1_USER_GUID and F1_TOKEN in .env or pass --guid / --token")
        raise SystemExit(1)

    logging.basicConfig(level=logging.INFO)
    result = collect_sync(args.guid, args.token, args.league, force=args.force)
    print(result)
