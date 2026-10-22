"""SQLite persistence. One file, no ORM, no migration framework.

Rationale: the project structures are small (a project has tens of shots) and we
want zero operational surface. JSON payloads for flexible fields, real columns
for anything we query or sort on.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    brief TEXT NOT NULL DEFAULT '',
    format TEXT NOT NULL DEFAULT '9:16',
    status TEXT NOT NULL DEFAULT 'draft',
    concept TEXT NOT NULL DEFAULT '',
    script TEXT NOT NULL DEFAULT '',
    style_guide TEXT NOT NULL DEFAULT '',
    music_path TEXT,
    settings TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    appearance TEXT NOT NULL DEFAULT '{}',
    base_image TEXT,
    voice_id TEXT,
    refs TEXT NOT NULL DEFAULT '[]',
    project_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS voices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    engine TEXT NOT NULL DEFAULT 'chatterbox',
    language TEXT NOT NULL DEFAULT 'fr',
    ref_audio TEXT,
    transcript TEXT NOT NULL DEFAULT '',
    params TEXT NOT NULL DEFAULT '{}',
    character_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shots (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'b_roll',
    title TEXT NOT NULL DEFAULT '',
    duration_s REAL NOT NULL DEFAULT 5.0,
    dialogue TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL DEFAULT '',
    camera TEXT NOT NULL DEFAULT '',
    character_id TEXT,
    voice_id TEXT,
    transition TEXT NOT NULL DEFAULT 'cut',
    status TEXT NOT NULL DEFAULT 'draft',
    selected_artifact TEXT,
    params TEXT NOT NULL DEFAULT '{}',
    qc TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shots_project ON shots(project_id, idx);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    shot_id TEXT,
    type TEXT NOT NULL,
    engine TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'queued',
    progress REAL NOT NULL DEFAULT 0,
    stage TEXT NOT NULL DEFAULT '',
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    provider TEXT NOT NULL DEFAULT 'local',
    gpu TEXT NOT NULL DEFAULT 'CPU',
    gpu_seconds REAL NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    simulated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    job_id TEXT,
    project_id TEXT,
    shot_id TEXT,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    mime TEXT NOT NULL DEFAULT 'application/octet-stream',
    bytes INTEGER NOT NULL DEFAULT 0,
    meta TEXT NOT NULL DEFAULT '{}',
    selected INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifacts_shot ON artifacts(shot_id);

CREATE TABLE IF NOT EXISTS exports (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    job_id TEXT,
    path TEXT NOT NULL,
    spec TEXT NOT NULL DEFAULT '{}',
    duration_s REAL NOT NULL DEFAULT 0,
    qc TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cost_events (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    job_id TEXT,
    provider TEXT NOT NULL,
    gpu TEXT NOT NULL,
    gpu_seconds REAL NOT NULL DEFAULT 0,
    rate_usd_hr REAL NOT NULL DEFAULT 0,
    usd REAL NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""

JSON_COLUMNS = {
    "projects": {"settings"},
    "characters": {"appearance", "refs"},
    "voices": {"params"},
    "shots": {"params", "qc"},
    "jobs": {"params"},
    "artifacts": {"meta"},
    "exports": {"spec", "qc"},
}

_local = threading.local()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _configure(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")


def connect() -> sqlite3.Connection:
    """Per-thread connection (the job worker is a different thread than HTTP)."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        path: Path = get_settings().db_path
        path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None => autocommit. Without it, a long-lived connection
        # can keep a read snapshot open in WAL mode and serve stale rows after a
        # worker thread commits.
        conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30, isolation_level=None)
        _configure(conn)
        _local.conn = conn
    return conn


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    """Explicit write transaction (connections are in autocommit mode)."""
    conn = connect()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def init_db() -> None:
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()


def row_to_dict(table: str, row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for col in JSON_COLUMNS.get(table, set()):
        if col in data and isinstance(data[col], str):
            try:
                data[col] = json.loads(data[col]) if data[col] else {}
            except json.JSONDecodeError:
                data[col] = {}
    return data


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def insert(table: str, data: dict[str, Any]) -> dict[str, Any]:
    payload = {}
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            payload[key] = dumps(value)
        elif isinstance(value, bool):
            payload[key] = int(value)
        else:
            payload[key] = value
    cols = ", ".join(payload)
    placeholders = ", ".join("?" for _ in payload)
    with tx() as conn:
        conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", tuple(payload.values()))
    return get(table, data["id"]) or {}


def get(table: str, row_id: str) -> dict[str, Any] | None:
    cur = connect().execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,))
    rows = cur.fetchall()  # fetchall + close: an open statement pins a WAL snapshot
    cur.close()
    return row_to_dict(table, rows[0]) if rows else None


def find(table: str, where: str = "", args: tuple = (), order: str = "created_at DESC", limit: int | None = None) -> list[dict[str, Any]]:
    sql = f"SELECT * FROM {table}"
    if where:
        sql += f" WHERE {where}"
    if order:
        sql += f" ORDER BY {order}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur = connect().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return [row_to_dict(table, r) for r in rows]  # type: ignore[misc]


def update(table: str, row_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    if not data:
        return get(table, row_id)
    payload = {}
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            payload[key] = dumps(value)
        elif isinstance(value, bool):
            payload[key] = int(value)
        else:
            payload[key] = value
    sets = ", ".join(f"{k} = ?" for k in payload)
    with tx() as conn:
        conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*payload.values(), row_id))
    return get(table, row_id)


def fetchone(sql: str, args: tuple = ()) -> sqlite3.Row | None:
    """Single-row query that always closes its cursor."""
    cur = connect().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return rows[0] if rows else None


def delete(table: str, row_id: str) -> bool:
    with tx() as conn:
        cur = conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
    return cur.rowcount > 0
