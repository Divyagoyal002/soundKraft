"""SQLite storage for users, sessions, rounds, trials and reference scores."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL,
    birth_year INTEGER,
    education_years INTEGER,
    settings_json TEXT NOT NULL DEFAULT '{}',
    consent_at TEXT NOT NULL,
    share_with_caregiver INTEGER NOT NULL DEFAULT 1,
    is_synthetic INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    device_json TEXT NOT NULL DEFAULT '{}',
    settings_json TEXT NOT NULL DEFAULT '{}',
    features_json TEXT,
    composite REAL,
    points INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    game TEXT NOT NULL,
    round_index INTEGER NOT NULL,
    level INTEGER NOT NULL,
    config_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    accuracy REAL,
    median_rt_ms REAL
);

CREATE TABLE IF NOT EXISTS trials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    trial_index INTEGER NOT NULL,
    stimulus_json TEXT NOT NULL DEFAULT '{}',
    response TEXT,
    correct INTEGER NOT NULL DEFAULT 0,
    timed_out INTEGER NOT NULL DEFAULT 0,
    rt_ms REAL,
    first_touch_ms REAL,
    tap_duration_ms REAL,
    swipe_ms REAL,
    swipe_px REAL,
    touch_x REAL,
    touch_y REAL,
    off_target_touches INTEGER NOT NULL DEFAULT 0,
    wrong_taps INTEGER NOT NULL DEFAULT 0,
    input_mode TEXT,
    error_type TEXT
);

CREATE TABLE IF NOT EXISTS reference_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    instrument TEXT NOT NULL,
    score REAL NOT NULL,
    max_score REAL NOT NULL,
    assessed_at TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS adaptations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    round_id INTEGER REFERENCES rounds(id) ON DELETE SET NULL,
    setting TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_rounds_session ON rounds(session_id);
CREATE INDEX IF NOT EXISTS idx_trials_round ON trials(round_id);
"""

TRIAL_FIELDS = [
    "trial_index", "stimulus_json", "response", "correct", "timed_out", "rt_ms",
    "first_touch_ms", "tap_duration_ms", "swipe_ms", "swipe_px", "touch_x", "touch_y",
    "off_target_touches", "wrong_taps", "input_mode", "error_type",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


# Columns added after the first release: (table, column, SQL definition).
MIGRATIONS = [
    ("trials", "wrong_taps", "INTEGER NOT NULL DEFAULT 0"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns that older databases are missing (CREATE TABLE IF NOT EXISTS won't)."""
    for table, column, definition in MIGRATIONS:
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.commit()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


# ---------------------------------------------------------------- users

def create_user(conn, display_name: str, birth_year: int | None, education_years: int | None,
                settings: dict, share_with_caregiver: bool = True, is_synthetic: bool = False,
                created_at: str | None = None) -> int:
    ts = created_at or now_iso()
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO users (display_name, birth_year, education_years, settings_json, consent_at,"
            " share_with_caregiver, is_synthetic, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (display_name, birth_year, education_years, json.dumps(settings), ts,
             int(share_with_caregiver), int(is_synthetic), ts),
        )
    return cur.lastrowid


def get_user(conn, user_id: int) -> dict | None:
    user = _row(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
    if user:
        user["settings"] = json.loads(user.pop("settings_json"))
    return user


def list_users(conn, shared_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM users"
    if shared_only:
        sql += " WHERE share_with_caregiver = 1"
    users = [dict(r) for r in conn.execute(sql + " ORDER BY display_name")]
    for u in users:
        u["settings"] = json.loads(u.pop("settings_json"))
    return users


def update_user_settings(conn, user_id: int, settings: dict) -> None:
    with transaction(conn):
        conn.execute("UPDATE users SET settings_json = ? WHERE id = ?", (json.dumps(settings), user_id))


def delete_user(conn, user_id: int) -> None:
    with transaction(conn):
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


# ---------------------------------------------------------------- sessions

def create_session(conn, user_id: int, settings: dict, device: dict | None = None,
                   started_at: str | None = None) -> int:
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO sessions (user_id, started_at, device_json, settings_json) VALUES (?,?,?,?)",
            (user_id, started_at or now_iso(), json.dumps(device or {}), json.dumps(settings)),
        )
    return cur.lastrowid


def get_session(conn, session_id: int) -> dict | None:
    s = _row(conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone())
    if s:
        s["settings"] = json.loads(s.pop("settings_json"))
        s["device"] = json.loads(s.pop("device_json"))
        s["features"] = json.loads(s.pop("features_json")) if s["features_json"] else None
    return s


def finish_session(conn, session_id: int, features: dict, composite: float | None, points: int,
                   ended_at: str | None = None) -> None:
    with transaction(conn):
        conn.execute(
            "UPDATE sessions SET ended_at = ?, features_json = ?, composite = ?, points = ? WHERE id = ?",
            (ended_at or now_iso(), json.dumps(features), composite, points, session_id),
        )


def user_sessions(conn, user_id: int, finished_only: bool = True) -> list[dict]:
    sql = "SELECT * FROM sessions WHERE user_id = ?"
    if finished_only:
        sql += " AND ended_at IS NOT NULL"
    out = []
    for r in conn.execute(sql + " ORDER BY started_at, id", (user_id,)):
        s = dict(r)
        s["settings"] = json.loads(s.pop("settings_json"))
        s["device"] = json.loads(s.pop("device_json"))
        s["features"] = json.loads(s.pop("features_json")) if s["features_json"] else None
        out.append(s)
    return out


# ---------------------------------------------------------------- rounds & trials

def create_round(conn, session_id: int, game: str, round_index: int, level: int, round_config: dict,
                 started_at: str | None = None) -> int:
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO rounds (session_id, game, round_index, level, config_json, started_at)"
            " VALUES (?,?,?,?,?,?)",
            (session_id, game, round_index, level, json.dumps(round_config), started_at or now_iso()),
        )
    return cur.lastrowid


def get_round(conn, round_id: int) -> dict | None:
    r = _row(conn.execute("SELECT * FROM rounds WHERE id = ?", (round_id,)).fetchone())
    if r:
        r["config"] = json.loads(r.pop("config_json"))
    return r


def session_rounds(conn, session_id: int, game: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM rounds WHERE session_id = ?", [session_id]
    if game:
        sql += " AND game = ?"
        args.append(game)
    out = []
    for r in conn.execute(sql + " ORDER BY id", args):
        d = dict(r)
        d["config"] = json.loads(d.pop("config_json"))
        out.append(d)
    return out


def last_completed_level(conn, user_id: int, game: str) -> int | None:
    """Level of the most recent completed round of `game` for this user, in any session."""
    row = conn.execute(
        "SELECT r.level FROM rounds r JOIN sessions s ON s.id = r.session_id"
        " WHERE s.user_id = ? AND r.game = ? AND r.ended_at IS NOT NULL ORDER BY r.id DESC LIMIT 1",
        (user_id, game),
    ).fetchone()
    return row["level"] if row else None


def save_trials(conn, round_id: int, trials: list[dict], accuracy: float | None,
                median_rt_ms: float | None, ended_at: str | None = None) -> None:
    rows = []
    for t in trials:
        t = dict(t)
        t["stimulus_json"] = json.dumps(t.pop("stimulus", {}))
        rows.append([round_id] + [t.get(f) for f in TRIAL_FIELDS])
    placeholders = ",".join("?" * (len(TRIAL_FIELDS) + 1))
    with transaction(conn):
        conn.execute("DELETE FROM trials WHERE round_id = ?", (round_id,))
        conn.executemany(
            f"INSERT INTO trials (round_id, {', '.join(TRIAL_FIELDS)}) VALUES ({placeholders})", rows
        )
        conn.execute(
            "UPDATE rounds SET ended_at = ?, accuracy = ?, median_rt_ms = ? WHERE id = ?",
            (ended_at or now_iso(), accuracy, median_rt_ms, round_id),
        )


def round_trials(conn, round_id: int) -> list[dict]:
    out = []
    for r in conn.execute("SELECT * FROM trials WHERE round_id = ? ORDER BY trial_index", (round_id,)):
        t = dict(r)
        t["stimulus"] = json.loads(t.pop("stimulus_json"))
        out.append(t)
    return out


def session_trials(conn, session_id: int) -> list[dict]:
    """All trials of a session joined with their round metadata (flat rows for analysis)."""
    sql = (
        "SELECT t.*, r.game, r.round_index, r.level FROM trials t JOIN rounds r ON r.id = t.round_id"
        " WHERE r.session_id = ? ORDER BY r.id, t.trial_index"
    )
    out = []
    for r in conn.execute(sql, (session_id,)):
        t = dict(r)
        t["stimulus"] = json.loads(t.pop("stimulus_json"))
        out.append(t)
    return out


# ---------------------------------------------------------------- reference scores & adaptations

def add_reference_score(conn, user_id: int, instrument: str, score: float, max_score: float,
                        assessed_at: str, notes: str | None = None) -> int:
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO reference_scores (user_id, instrument, score, max_score, assessed_at, notes)"
            " VALUES (?,?,?,?,?,?)",
            (user_id, instrument, score, max_score, assessed_at, notes),
        )
    return cur.lastrowid


def reference_scores(conn, user_id: int | None = None) -> list[dict]:
    if user_id is None:
        rows = conn.execute("SELECT * FROM reference_scores ORDER BY user_id, assessed_at")
    else:
        rows = conn.execute("SELECT * FROM reference_scores WHERE user_id = ? ORDER BY assessed_at", (user_id,))
    return [dict(r) for r in rows]


def log_adaptation(conn, user_id: int, round_id: int | None, setting: str, old: Any, new: Any,
                   reason: str) -> None:
    with transaction(conn):
        conn.execute(
            "INSERT INTO adaptations (user_id, round_id, setting, old_value, new_value, reason, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (user_id, round_id, setting, json.dumps(old), json.dumps(new), reason, now_iso()),
        )


def user_adaptations(conn, user_id: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM adaptations WHERE user_id = ? ORDER BY id", (user_id,))
    return [dict(r) for r in rows]
