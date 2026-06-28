"""
SQLite database layer for F1 Fantasy Dashboard.

Stores users, league members, race results, budget history, and chip usage.
All writes go through helper functions; the dashboard reads via query functions.
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# Configurable so production can point at a persistent volume
# (e.g. F1_DB_PATH=/data/f1_data.db on a Railway volume).
DB_PATH = Path(os.environ.get("F1_DB_PATH") or (Path(__file__).resolve().parent / "f1_data.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(_SCHEMA)


_SCHEMA = """\
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    f1_guid         TEXT NOT NULL UNIQUE,
    f1_username     TEXT NOT NULL,
    f1_token        TEXT,
    token_expires_at REAL,
    created_at      REAL NOT NULL DEFAULT (strftime('%s','now')),
    last_login      REAL
);

CREATE TABLE IF NOT EXISTS user_leagues (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    league_id  INTEGER NOT NULL,
    league_name TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, league_id)
);

CREATE TABLE IF NOT EXISTS league_members (
    league_id   INTEGER NOT NULL,
    user_name   TEXT NOT NULL,
    guid        TEXT NOT NULL,
    team_no     INTEGER NOT NULL,
    team_name   TEXT NOT NULL,
    updated_at  REAL NOT NULL DEFAULT (strftime('%s','now')),
    PRIMARY KEY (league_id, guid, team_no)
);

CREATE TABLE IF NOT EXISTS race_results (
    league_id   INTEGER NOT NULL,
    race_round  INTEGER NOT NULL,
    user_name   TEXT NOT NULL,
    team_name   TEXT NOT NULL,
    points      REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (league_id, race_round, user_name, team_name)
);

CREATE TABLE IF NOT EXISTS budget_history (
    league_id   INTEGER NOT NULL,
    race_round  INTEGER NOT NULL,
    user_name   TEXT NOT NULL,
    team_val    REAL NOT NULL DEFAULT 0,
    team_bal    REAL NOT NULL DEFAULT 0,
    max_team_bal REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (league_id, race_round, user_name)
);

CREATE TABLE IF NOT EXISTS chip_usage (
    league_id   INTEGER NOT NULL,
    race_round  INTEGER NOT NULL,
    user_name   TEXT NOT NULL,
    team_name   TEXT NOT NULL,
    chip_name   TEXT NOT NULL,
    PRIMARY KEY (league_id, race_round, user_name, team_name, chip_name)
);
"""


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def upsert_user(f1_guid: str, f1_username: str, f1_token: str | None = None,
                token_expires_at: float | None = None) -> int:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO users (f1_guid, f1_username, f1_token, token_expires_at, last_login)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(f1_guid) DO UPDATE SET
                f1_username = excluded.f1_username,
                f1_token = COALESCE(excluded.f1_token, f1_token),
                token_expires_at = COALESCE(excluded.token_expires_at, token_expires_at),
                last_login = excluded.last_login
        """, (f1_guid, f1_username, f1_token, token_expires_at, time.time()))
        row = conn.execute("SELECT id FROM users WHERE f1_guid = ?", (f1_guid,)).fetchone()
        return row["id"]


def upsert_user_league(user_id: int, league_id: int, league_name: str = "") -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO user_leagues (user_id, league_id, league_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, league_id) DO UPDATE SET league_name = excluded.league_name
        """, (user_id, league_id, league_name))


def upsert_league_members(league_id: int, members: list[dict]) -> None:
    with get_conn() as conn:
        now = time.time()
        for m in members:
            conn.execute("""
                INSERT INTO league_members (league_id, user_name, guid, team_no, team_name, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(league_id, guid, team_no) DO UPDATE SET
                    user_name = excluded.user_name,
                    team_name = excluded.team_name,
                    updated_at = excluded.updated_at
            """, (league_id, m["user_name"], m["guid"], m["team_no"], m["team_name"], now))


def upsert_race_results(league_id: int, race_round: int, entries: list[dict]) -> None:
    with get_conn() as conn:
        for e in entries:
            conn.execute("""
                INSERT INTO race_results (league_id, race_round, user_name, team_name, points)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(league_id, race_round, user_name, team_name) DO UPDATE SET
                    points = excluded.points
            """, (league_id, race_round, e["user_name"], e["team_name"], e["points"]))


def upsert_budget(league_id: int, race_round: int, user_name: str,
                  team_val: float, team_bal: float, max_team_bal: float) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO budget_history (league_id, race_round, user_name, team_val, team_bal, max_team_bal)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(league_id, race_round, user_name) DO UPDATE SET
                team_val = excluded.team_val,
                team_bal = excluded.team_bal,
                max_team_bal = excluded.max_team_bal
        """, (league_id, race_round, user_name, team_val, team_bal, max_team_bal))


def upsert_chip(league_id: int, race_round: int, user_name: str,
                team_name: str, chip_name: str) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO chip_usage (league_id, race_round, user_name, team_name, chip_name)
            VALUES (?, ?, ?, ?, ?)
        """, (league_id, race_round, user_name, team_name, chip_name))


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


def get_user_by_guid(f1_guid: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE f1_guid = ?", (f1_guid,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_leagues(user_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT league_id, league_name FROM user_leagues WHERE user_id = ?", (user_id,)
        ).fetchall()
        return _rows_to_dicts(rows)


def get_league_members(league_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT user_name, guid, team_no, team_name FROM league_members WHERE league_id = ?",
            (league_id,)
        ).fetchall()
        return _rows_to_dicts(rows)


def get_league_member_names(league_id: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT user_name FROM league_members WHERE league_id = ? ORDER BY user_name",
            (league_id,)
        ).fetchall()
        return [r["user_name"] for r in rows]


def get_race_results(league_id: int) -> dict[int, list[dict]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT race_round, user_name, team_name, points FROM race_results "
            "WHERE league_id = ? ORDER BY race_round",
            (league_id,),
        ).fetchall()
    by_round: dict[int, list[dict]] = {}
    for r in rows:
        rd = r["race_round"]
        by_round.setdefault(rd, []).append({
            "user_name": r["user_name"], "team_name": r["team_name"], "points": r["points"],
        })
    return by_round


def get_budget_history(league_id: int) -> dict[str, dict[int, dict]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT race_round, user_name, team_val, team_bal, max_team_bal "
            "FROM budget_history WHERE league_id = ? ORDER BY race_round",
            (league_id,),
        ).fetchall()
    by_user: dict[str, dict[int, dict]] = {}
    for r in rows:
        by_user.setdefault(r["user_name"], {})[r["race_round"]] = {
            "team_val": r["team_val"], "team_bal": r["team_bal"],
            "max_team_bal": r["max_team_bal"],
        }
    return by_user


def get_chip_usage(league_id: int) -> dict[str, list[dict]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT race_round, user_name, team_name, chip_name FROM chip_usage "
            "WHERE league_id = ? ORDER BY race_round",
            (league_id,),
        ).fetchall()
    by_user: dict[str, list[dict]] = {}
    for r in rows:
        by_user.setdefault(r["user_name"], []).append({
            "race": r["race_round"], "team": r["team_name"], "chip": r["chip_name"],
        })
    return by_user


def get_collected_rounds(league_id: int) -> set[int]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT race_round FROM race_results WHERE league_id = ?", (league_id,)
        ).fetchall()
        return {r["race_round"] for r in rows}


def get_users_with_valid_tokens() -> list[dict]:
    now = time.time()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE f1_token IS NOT NULL AND token_expires_at > ?", (now,)
        ).fetchall()
        return _rows_to_dicts(rows)
