"""
EV Mitra — user_store.py
Lightweight SQLite-backed store for user profiles and verdict history.

Profiles are keyed by a browser-generated UUID stored in localStorage.
No authentication — MVP-grade privacy.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent if (BASE_DIR.parent / "data").exists() else BASE_DIR
DB_PATH = PROJECT_ROOT / "ev_mitra_users.db"


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    """Create tables if they don't exist. Called once at startup."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                user_id             TEXT PRIMARY KEY,
                created_at          TEXT NOT NULL,
                updated_at          TEXT NOT NULL,
                preferred_city      TEXT,
                preferred_car       TEXT,
                preferred_daily_km  INTEGER,
                preferred_occasional_km INTEGER,
                has_home_charging   INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS verdicts (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id             TEXT NOT NULL,
                timestamp           TEXT NOT NULL,
                city                TEXT,
                car                 TEXT,
                daily_km            INTEGER,
                occasional_km       INTEGER,
                daily_score         INTEGER,
                occasional_score    INTEGER,
                total_stations      INTEGER,
                verdict_text        TEXT,
                source_metadata     TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_verdicts_user
                ON verdicts(user_id, timestamp DESC);
        """)


def upsert_profile(user_id: str, prefs: dict) -> dict:
    """Create or update a user profile. Returns the saved profile."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        existing = con.execute(
            "SELECT * FROM profiles WHERE user_id = ?", (user_id,)
        ).fetchone()

        if existing:
            con.execute("""
                UPDATE profiles SET
                    updated_at              = ?,
                    preferred_city          = COALESCE(?, preferred_city),
                    preferred_car           = COALESCE(?, preferred_car),
                    preferred_daily_km      = COALESCE(?, preferred_daily_km),
                    preferred_occasional_km = COALESCE(?, preferred_occasional_km),
                    has_home_charging       = COALESCE(?, has_home_charging)
                WHERE user_id = ?
            """, (
                now,
                prefs.get("preferred_city"),
                prefs.get("preferred_car"),
                prefs.get("preferred_daily_km"),
                prefs.get("preferred_occasional_km"),
                int(prefs["has_home_charging"]) if "has_home_charging" in prefs else None,
                user_id,
            ))
        else:
            con.execute("""
                INSERT INTO profiles
                    (user_id, created_at, updated_at, preferred_city, preferred_car,
                     preferred_daily_km, preferred_occasional_km, has_home_charging)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, now, now,
                prefs.get("preferred_city"),
                prefs.get("preferred_car"),
                prefs.get("preferred_daily_km"),
                prefs.get("preferred_occasional_km"),
                int(prefs.get("has_home_charging", False)),
            ))

    return get_profile(user_id)


def get_profile(user_id: str) -> dict | None:
    """Return user profile dict, or None if not found."""
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
    if not row:
        return None
    return dict(row)


def save_verdict(user_id: str, verdict_data: dict):
    """Persist a completed verdict for history + diff tracking."""
    scores = verdict_data.get("scores", {})
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute("""
            INSERT INTO verdicts
                (user_id, timestamp, city, car, daily_km, occasional_km,
                 daily_score, occasional_score, total_stations,
                 verdict_text, source_metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, now,
            verdict_data.get("city"),
            verdict_data.get("car"),
            verdict_data.get("daily_km"),
            verdict_data.get("occasional_km"),
            scores.get("daily_score"),
            scores.get("occasional_score"),
            scores.get("total_stations"),
            verdict_data.get("verdict"),
            json.dumps(verdict_data.get("data_freshness", {})),
        ))


def get_last_verdict(user_id: str) -> dict | None:
    """Return the most recent verdict for this user, or None."""
    with _conn() as con:
        row = con.execute("""
            SELECT * FROM verdicts
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (user_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["source_metadata"] = json.loads(d.get("source_metadata") or "{}")
    except Exception:
        d["source_metadata"] = {}
    return d


def get_what_changed(user_id: str, new_verdict: dict) -> dict | None:
    """
    Diff the new verdict against the user's last verdict.
    Returns a dict of changes, or None if no previous verdict exists.
    """
    prev = get_last_verdict(user_id)
    if not prev:
        return None

    new_scores = new_verdict.get("scores", {})
    changes = {}

    # Score deltas
    daily_delta = new_scores.get("daily_score", 0) - (prev.get("daily_score") or 0)
    occ_delta = new_scores.get("occasional_score", 0) - (prev.get("occasional_score") or 0)
    station_delta = new_scores.get("total_stations", 0) - (prev.get("total_stations") or 0)

    if daily_delta != 0:
        changes["daily_score"] = {
            "from": prev.get("daily_score"),
            "to": new_scores.get("daily_score"),
            "delta": daily_delta,
        }
    if occ_delta != 0:
        changes["occasional_score"] = {
            "from": prev.get("occasional_score"),
            "to": new_scores.get("occasional_score"),
            "delta": occ_delta,
        }
    if station_delta != 0:
        changes["total_stations"] = {
            "from": prev.get("total_stations"),
            "to": new_scores.get("total_stations"),
            "delta": station_delta,
        }

    if not changes:
        return None

    return {
        "previous_check": prev.get("timestamp"),
        "previous_city": prev.get("city"),
        "previous_car": prev.get("car"),
        "changes": changes,
    }
