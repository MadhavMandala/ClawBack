"""Saved email (Nylas grant) and bank (Plaid) connections: ids, tokens, sync position, account names, timestamps.

Stored in the database `connections` table (db.py), one row per user and source. The whole connection, Nylas
grant id and Plaid access token included, is encrypted with Fernet (crypto.py, key CLAWBACK_SECRET_KEY). Each row
also has `lookup`, a keyed hash of the grant id or Plaid item id, indexed, so a webhook can find its user without
the ids being stored in clear. A row that won't decrypt (the key changed) counts as no connection and is logged.

The old plaintext file (backend/.local/connections.json, CLAWBACK_CONNECTIONS_FILE) is moved into the database
the first time the database opens, then deleted.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from pydantic import BaseModel

from . import config, crypto, db

log = logging.getLogger("clawback.connections")

SOURCES = ("email", "plaid")


def now() -> datetime:
    return datetime.now(timezone.utc)


class EmailConnection(BaseModel):
    grant_id: str  # Nylas grant; Nylas holds the provider tokens
    account: str | None = None  # the email address
    provider: str | None = None  # Nylas provider name: google, microsoft, yahoo, icloud, imap, ews
    connected_at: datetime
    last_sync: datetime | None = None
    error: str | None = None
    needs_reconnect: bool = False
    # Reading works but saving drafts was refused (the grant lacks a compose / write scope). Connecting email
    # again with the drafts permission clears it; sync keeps working meanwhile.
    needs_reconsent: bool = False
    reconsent_reason: str | None = None


class PlaidConnection(BaseModel):
    access_token: str
    item_id: str
    institution: str | None = None
    cursor: str | None = None  # last /transactions/sync cursor
    connected_at: datetime
    last_sync: datetime | None = None
    error: str | None = None
    needs_reconnect: bool = False


class UserConnections(BaseModel):
    email: EmailConnection | None = None
    plaid: PlaidConnection | None = None

    def any(self) -> bool:
        return self.email is not None or self.plaid is not None


_MODELS = {"email": EmailConnection, "plaid": PlaidConnection}


def _external_id(source: str, conn: EmailConnection | PlaidConnection) -> str:
    return conn.grant_id if source == "email" else conn.item_id  # type: ignore[union-attr]


def lookup_key(source: str, external_id: str) -> str:
    return crypto.lookup(f"{source}:{external_id}")


def _decode(source: str, blob: bytes):
    try:
        return _MODELS[source].model_validate_json(crypto.decrypt(blob))
    except (crypto.CryptoError, ValueError) as exc:
        log.warning("a saved %s connection could not be read (%s); treating it as not connected", source, exc)
        return None


def get(user_id: str) -> UserConnections:
    out = UserConnections()
    for row in db.query("SELECT source, secret FROM connections WHERE user_id = ?", (user_id,)):
        if row["source"] in _MODELS:
            setattr(out, row["source"], _decode(row["source"], row["secret"]))
    return out


def _write(c, user_id: str, source: str, conn) -> None:
    c.execute(
        "INSERT INTO connections (user_id, source, lookup, secret, updated_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (user_id, source) DO UPDATE SET lookup = excluded.lookup, secret = excluded.secret, "
        "updated_at = excluded.updated_at",
        (user_id, source, lookup_key(source, _external_id(source, conn)),
         crypto.encrypt(conn.model_dump_json().encode()), db.iso(now())),
    )


def _set(user_id: str, source: str, conn) -> None:
    with db.tx() as c:
        if conn is None:
            c.execute("DELETE FROM connections WHERE user_id = ? AND source = ?", (user_id, source))
        else:
            _write(c, user_id, source, conn)


def set_email(user_id: str, conn: EmailConnection | None) -> None:
    _set(user_id, "email", conn)


def set_plaid(user_id: str, conn: PlaidConnection | None) -> None:
    _set(user_id, "plaid", conn)


# Sync code saves through these, so a disconnect that lands mid-sync can't bring the token back, and a
# "needs a new sign-in" flag that a webhook or the grant check set mid-sync isn't cleared by the sync's older copy.
# Only a new connection (set_email / set_plaid) or mark_reconnect(needs=False) clears that flag.

def _update(user_id: str, source: str, conn, same) -> bool:
    with db.tx() as c:
        row = c.execute("SELECT secret FROM connections WHERE user_id = ? AND source = ?",
                        (user_id, source)).fetchone()
        current = _decode(source, row["secret"]) if row else None
        if current is None or not same(current, conn):
            return False
        if current.needs_reconnect and not conn.needs_reconnect:
            conn = conn.model_copy(update={"needs_reconnect": True, "error": current.error})
        _write(c, user_id, source, conn)
        return True


def update_email(user_id: str, conn: EmailConnection) -> None:
    _update(user_id, "email", conn, lambda cur, new: (cur.grant_id, cur.connected_at) == (new.grant_id, new.connected_at))


def update_plaid(user_id: str, conn: PlaidConnection) -> None:
    _update(user_id, "plaid", conn, lambda cur, new: cur.item_id == new.item_id)


# --- Lookups for webhooks and the nightly job --------------------------------------------------------

def find_users(source: str, external_id: str) -> list[str]:
    """Users whose saved connection has this Nylas grant id (source "email") or Plaid item id ("plaid").

    Usually one. Nylas gives the same grant to the same inbox, so one person connecting their inbox in two
    browsers (two sessions) shares a grant."""
    if not external_id:
        return []
    return [r["user_id"] for r in db.query("SELECT user_id FROM connections WHERE source = ? AND lookup = ? "
                                           "ORDER BY user_id", (source, lookup_key(source, external_id)))]


def find_user(source: str, external_id: str) -> str | None:
    users = find_users(source, external_id)
    return users[0] if users else None


def shared(source: str, external_id: str, user_id: str) -> bool:
    """True when another user still uses this grant or item, so it must not be deleted at the provider."""
    return any(u != user_id for u in find_users(source, external_id))


def users_with_connections() -> list[str]:
    return [r["user_id"] for r in db.query("SELECT DISTINCT user_id FROM connections ORDER BY user_id")]


def mark_reconnect(user_id: str, source: str, message: str, needs: bool = True) -> bool:
    """Flag a saved connection as needing a new sign-in (or clear the flag). False when there is no connection."""
    with db.tx() as c:
        row = c.execute("SELECT secret FROM connections WHERE user_id = ? AND source = ?",
                        (user_id, source)).fetchone()
        conn = _decode(source, row["secret"]) if row else None
        if conn is None:
            return False
        conn.needs_reconnect, conn.error = needs, (message if needs else None)
        _write(c, user_id, source, conn)
        return True


def delete_user(user_id: str) -> int:
    return db.execute("DELETE FROM connections WHERE user_id = ?", (user_id,))


# --- One-time move of the old plaintext file ----------------------------------------------------------

def migrate_legacy_file() -> int:
    """Move connections from the old plaintext JSON file into the database, then delete the file.

    Users from the file get a "single" user row (they came from the one-user prototype). Returns how many
    connections moved. A file that can't be read is renamed to .bad and left alone.
    """
    path = config.settings.connections_path
    if not path.is_file():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        users = {uid: UserConnections.model_validate(c) for uid, c in (raw.get("users") or {}).items()}
    except (ValueError, AttributeError):
        path.replace(path.with_name(path.name + ".bad"))
        log.warning("the old connections file could not be read; renamed it to %s.bad", path.name)
        return 0
    moved = 0
    stamp = db.iso(now())
    with db.tx() as c:
        for uid, conns in users.items():
            c.execute("INSERT OR IGNORE INTO users (id, kind, created_at, last_seen) VALUES (?, 'single', ?, ?)",
                      (uid, stamp, stamp))
            for source in SOURCES:
                conn = getattr(conns, source)
                if conn is not None:
                    _write(c, uid, source, conn)
                    moved += 1
    for uid, conns in users.items():  # read back before the plaintext copy goes
        if get(uid) != conns:
            log.warning("moving the old connections file did not round-trip; left it in place")
            return moved
    path.unlink()
    log.warning("moved %d saved connections from %s into the database (encrypted) and deleted the file",
                moved, path)
    return moved


db.on_open(migrate_legacy_file)
