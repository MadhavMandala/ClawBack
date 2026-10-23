"""Saved email (Nylas grant) and bank (Plaid) connections: ids, tokens, sync position, account names, timestamps.

Kept in a JSON file (settings.connections_path, default backend/.local/connections.json, git-ignored) so a
restart doesn't lose them. MISSING [token-encryption]: the Plaid access token in that file is plaintext.
A Nylas grant id is only usable together with NYLAS_API_KEY, which stays in backend/.env.
MISSING [database]: this moves to an encrypted `connections` table.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone

from pydantic import BaseModel

from . import config


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


_lock = threading.RLock()


def _load_all() -> dict[str, UserConnections]:
    path = config.settings.connections_path
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {uid: UserConnections.model_validate(c) for uid, c in raw.get("users", {}).items()}
    except (ValueError, AttributeError):
        # Unreadable file: set it aside rather than overwrite it, and start with no connections.
        os.replace(path, path.with_name(path.name + ".bad"))
        return {}


def _save_all(users: dict[str, UserConnections]) -> None:
    path = config.settings.connections_path
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "users": {uid: c.model_dump(mode="json") for uid, c in users.items() if c.any()}}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def get(user_id: str) -> UserConnections:
    with _lock:
        return _load_all().get(user_id, UserConnections())


def set_email(user_id: str, conn: EmailConnection | None) -> None:
    with _lock:
        users = _load_all()
        users.setdefault(user_id, UserConnections()).email = conn
        _save_all(users)


def set_plaid(user_id: str, conn: PlaidConnection | None) -> None:
    with _lock:
        users = _load_all()
        users.setdefault(user_id, UserConnections()).plaid = conn
        _save_all(users)


# Sync code saves through these, so a disconnect that lands mid-sync can't bring the token back.

def update_email(user_id: str, conn: EmailConnection) -> None:
    with _lock:
        users = _load_all()
        current = users.get(user_id)
        if current and current.email and (current.email.grant_id, current.email.connected_at) == (
                conn.grant_id, conn.connected_at):
            current.email = conn
            _save_all(users)


def update_plaid(user_id: str, conn: PlaidConnection) -> None:
    with _lock:
        users = _load_all()
        current = users.get(user_id)
        if current and current.plaid and current.plaid.item_id == conn.item_id:
            current.plaid = conn
            _save_all(users)
