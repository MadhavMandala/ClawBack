"""The database: one SQLite file (stdlib sqlite3), at CLAWBACK_DB_PATH (default backend/.local/clawback.db).

One uvicorn process is the deploy target. The nightly job (python -m clawback.nightly) may run as a second
process on the same file, so the file uses WAL mode with a busy timeout, and every write is one short transaction.

Tables
  users        id, kind (visitor | single | system), created_at, last_seen, version, data
               data = the user's UserData as JSON, encrypted (store.py; real email bodies are never in it).
               version goes up on every save, so the API notices when the nightly job changed a user.
  sessions     token_hash (SHA-256 of the session id the browser holds), user_id, created_at
  session_log  ip_hash, at: one row per session created, for the per-IP limit (kept a day)
  connections  user_id, source (email | plaid), lookup, secret, updated_at
               secret = the whole connection (grant id or access token included), encrypted.
               lookup = keyed hash of the Nylas grant id or Plaid item id, indexed, for webhooks.
  spend        day, user_id, usd, calls: model spend per UTC day, for the daily caps (budget.py)
  alerts       id, user_id, key, kind, ref, title, message, amount, created_at, seen_at, silent (alerts.py)
  meta         key, value: e.g. the last nightly run
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from . import config

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0,
    data BLOB
);
CREATE INDEX IF NOT EXISTS users_last_seen ON users (last_seen);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions (user_id);

-- The Gmail add-on's read-only token (sessions.py): one per user, stored only as a SHA-256 hash.
CREATE TABLE IF NOT EXISTS addon_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_log (
    ip_hash TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS session_log_ip ON session_log (ip_hash, at);

CREATE TABLE IF NOT EXISTS connections (
    user_id TEXT NOT NULL,
    source TEXT NOT NULL,
    lookup TEXT NOT NULL,
    secret BLOB NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, source)
);
CREATE INDEX IF NOT EXISTS connections_lookup ON connections (source, lookup);

CREATE TABLE IF NOT EXISTS spend (
    day TEXT NOT NULL,
    user_id TEXT NOT NULL,
    usd REAL NOT NULL DEFAULT 0,
    calls INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, user_id)
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,
    kind TEXT NOT NULL,
    ref TEXT,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    seen_at TEXT,
    silent INTEGER NOT NULL DEFAULT 0,
    UNIQUE (user_id, key)
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat(timespec="seconds")


_lock = threading.RLock()
_conn: sqlite3.Connection | None = None
_path: Path | None = None
_after_open: list = []  # callbacks run once per newly opened file (connections.py migrates the old JSON file)


def on_open(fn) -> None:
    _after_open.append(fn)


def _open(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(SCHEMA)
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(alerts)")}
    if "silent" not in columns:  # version 1 files
        conn.execute("ALTER TABLE alerts ADD COLUMN silent INTEGER NOT NULL DEFAULT 0")
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    return conn


def connection() -> sqlite3.Connection:
    """The shared connection for the current CLAWBACK_DB_PATH (re-opened if the setting changed, as in tests)."""
    global _conn, _path
    path = Path(config.settings.db_path)
    with _lock:
        if _conn is None or _path != path:
            close()
            _conn, _path = _open(path), path
            for fn in _after_open:
                fn()
        return _conn


def close() -> None:
    global _conn, _path
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            finally:
                _conn, _path = None, None


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    """One write transaction (BEGIN IMMEDIATE, so a second process waits instead of failing mid-way)."""
    with _lock:
        c = connection()
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
        except BaseException:
            c.execute("ROLLBACK")
            raise
        c.execute("COMMIT")


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with _lock:
        return connection().execute(sql, params).fetchall()


def one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    with _lock:
        return connection().execute(sql, params).fetchone()


def execute(sql: str, params: tuple = ()) -> int:
    """A single-statement write. Returns the number of rows changed."""
    with _lock:
        return connection().execute(sql, params).rowcount


def get_meta(key: str) -> str | None:
    row = one("SELECT value FROM meta WHERE key = ?", (key,))
    return row["value"] if row else None


def set_meta(key: str, value: str) -> None:
    execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (key, value))
