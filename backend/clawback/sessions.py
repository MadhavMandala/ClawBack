"""Sessions: each visitor gets their own demo, with no login. Real connections still work inside a session.

How it works
  - POST /api/session makes a session: a random id (secrets.token_urlsafe(32)) for the browser, and a separate
    random user id for the data. Only the SHA-256 of the session id is stored, so the database alone can't be
    used to take over a session. The new user gets the demo data (demo.seed) and the id goes back once.
  - The frontend keeps the id in localStorage and sends it as the X-ClawBack-Session header on every request.
    A header, not a cookie: the frontend and the API are on different domains, where third-party cookies fail.
  - current_user (a FastAPI dependency) resolves the header to the user id. A missing, unknown or idle-expired
    session gets 401 {"detail": "session expired"}, and the frontend makes a new one and retries once.
  - Each user's requests run one at a time (user_scope), and the user is saved at the end of each request.

Protecting the hosted demo (all settings, see config.py)
  - CLAWBACK_SESSIONS_PER_IP_HOUR (default 20): new sessions per client address per hour. The address is stored
    only as a keyed hash. Behind a proxy, run uvicorn with --forwarded-allow-ips set to the proxy's address, so
    request.client is the visitor and not the proxy.
  - CLAWBACK_SESSION_IDLE_DAYS (default 14): a session nobody has used for that long expires, and prune() (run by
    the nightly job) deletes it completely, the same as DELETE /api/me: its Nylas grant is deleted and its Plaid
    item removed (best effort), then every row. Connected sessions are not kept longer: an abandoned anonymous
    session shouldn't keep reading anyone's mail, and the Nylas Sandbox only allows 5 grants.
  - Daily model spend caps per session and overall: budget.py.

CLAWBACK_SESSIONS=single keeps the old behaviour for local development: no header needed, everyone is the user
"demo", and saved connections are synced on startup. Hosted deploys use the default, "visitor".
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Annotated, AsyncIterator

from fastapi import Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from . import alerts, budget, config, connect, connections, crypto, db, demo
from .sources import nylas, plaid
from .store import store

HEADER = "X-ClawBack-Session"
SINGLE_USER = "demo"
EXPIRED = "session expired"
TOUCH_EVERY = timedelta(minutes=5)  # last_seen is written at most this often per user

_single_ready = False
_single_lock = threading.Lock()


class TooManySessions(Exception):
    pass


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _parse(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp)


# --- Create and resolve ------------------------------------------------------------------------------

def ensure_single() -> str:
    """Single-user mode: make sure the "demo" user has a row, so its data is saved."""
    global _single_ready
    with _single_lock:
        if not _single_ready:
            stamp = db.iso(db.now())
            db.execute("INSERT OR IGNORE INTO users (id, kind, created_at, last_seen) VALUES (?, 'single', ?, ?)",
                       (SINGLE_USER, stamp, stamp))
            _single_ready = True
    return SINGLE_USER


def create(ip: str | None) -> str:
    """A new visitor session with fresh demo data. Returns the session id for the browser (shown once)."""
    s = config.settings
    stamp = db.now()
    token, user_id = secrets.token_urlsafe(32), "u_" + secrets.token_hex(12)
    with db.tx() as c:
        if s.sessions_per_ip_hour > 0 and ip:
            ip_hash = crypto.lookup(f"ip:{ip}")
            since = db.iso(stamp - timedelta(hours=1))
            n = c.execute("SELECT COUNT(*) FROM session_log WHERE ip_hash = ? AND at > ?", (ip_hash, since)).fetchone()[0]
            if n >= s.sessions_per_ip_hour:
                raise TooManySessions()
            c.execute("INSERT INTO session_log (ip_hash, at) VALUES (?, ?)", (ip_hash, db.iso(stamp)))
        c.execute("INSERT INTO users (id, kind, created_at, last_seen) VALUES (?, 'visitor', ?, ?)",
                  (user_id, db.iso(stamp), db.iso(stamp)))
        c.execute("INSERT INTO sessions (token_hash, user_id, created_at) VALUES (?, ?, ?)",
                  (_hash(token), user_id, db.iso(stamp)))
    if s.autoseed_demo:
        demo.seed(user_id)
        store.save(user_id)
    return token


def resolve(token: str | None) -> str:
    """The user id for a session id, or HTTPException 401 "session expired"."""
    if config.settings.single_user:
        return ensure_single()
    token = (token or "").strip()
    if not 20 <= len(token) <= 200:
        raise HTTPException(401, EXPIRED)
    row = db.one("SELECT s.user_id, u.last_seen FROM sessions s JOIN users u ON u.id = s.user_id "
                 "WHERE s.token_hash = ?", (_hash(token),))
    if row is None:
        raise HTTPException(401, EXPIRED)
    now, last = db.now(), _parse(row["last_seen"])
    if now - last > timedelta(days=config.settings.session_idle_days):
        raise HTTPException(401, EXPIRED)  # prune() deletes it
    if now - last > TOUCH_EVERY:
        db.execute("UPDATE users SET last_seen = ? WHERE id = ?", (db.iso(now), row["user_id"]))
    return row["user_id"]


# --- One user's requests, one at a time ----------------------------------------------------------------

_locks: dict[tuple[int, str], asyncio.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(user_id: str) -> asyncio.Lock:
    key = (id(asyncio.get_running_loop()), user_id)
    with _locks_guard:
        if key not in _locks:
            _locks[key] = asyncio.Lock()
        return _locks[key]


def _enter(user_id: str) -> None:
    store.refresh(user_id)  # the nightly job may have changed this user
    connect.ensure_fresh(user_id)


@asynccontextmanager
async def user_scope(user_id: str) -> AsyncIterator[str]:
    """Run one piece of work for a user: no other request or webhook for that user runs meanwhile, the user is
    reloaded first if another process changed it, and it is saved afterwards (also after an error)."""
    async with _lock_for(user_id):
        await run_in_threadpool(_enter, user_id)
        try:
            yield user_id
        finally:
            await run_in_threadpool(store.save, user_id)


async def current_user(request: Request) -> AsyncIterator[str]:
    """FastAPI dependency: the user behind the X-ClawBack-Session header (single-user mode: "demo")."""
    user_id = await run_in_threadpool(resolve, request.headers.get(HEADER))
    async with user_scope(user_id):
        yield user_id


UserId = Annotated[str, Depends(current_user)]


# --- Settings page, delete, prune -----------------------------------------------------------------------

def info(user_id: str) -> dict:
    """GET /api/me. Never includes tokens, grant ids or the session id."""
    row = db.one("SELECT kind, created_at, last_seen FROM users WHERE id = ?", (user_id,))
    u, c, s = store.user(user_id), connections.get(user_id), config.settings
    e, p = c.email, c.plaid
    return {
        "session": {
            "kind": row["kind"] if row else ("single" if s.single_user else "visitor"),
            "created_at": row["created_at"] if row else None,
            "last_seen": row["last_seen"] if row else None,
            "deleted_after_idle_days": s.session_idle_days,
        },
        "mode": u.mode,
        "connections": {
            "email": {"connected": e is not None, "account": e.account if e else None,
                      "provider": e.provider if e else None, "needs_reconnect": bool(e and e.needs_reconnect)},
            "plaid": {"connected": p is not None, "institution": p.institution if p else None,
                      "needs_reconnect": bool(p and p.needs_reconnect)},
        },
        "counts": {
            "subscriptions": sum(1 for x in u.subscriptions.values() if x.kind != "bill"),
            "bills": sum(1 for x in u.subscriptions.values() if x.kind == "bill"),
            "findings": len(u.findings),
            "emails": len(u.emails),
            "transactions": len(u.transactions),
            "alerts": alerts.count(user_id),
        },
        "model_spend_today_usd": round(budget.spent(user_id), 4),
        "model_daily_limit_usd": s.session_daily_usd if s.session_daily_usd > 0 else None,
    }


def delete(user_id: str) -> dict:
    """DELETE /api/me: end the connections at Nylas and Plaid (best effort), then delete every row for this user."""
    c, u = connections.get(user_id), store.user(user_id)
    removed: dict = {}
    if c.email and connections.shared("email", c.email.grant_id, user_id):
        removed["email_connection"] = "forgotten here; kept at Nylas because another session uses the same inbox"
    elif c.email:
        ok = config.settings.email_configured() and nylas.delete_grant(user_id, c.email.grant_id)
        removed["email_connection"] = ("deleted at Nylas" if ok else
                                       "forgotten here; Nylas didn't confirm deleting the grant")
    if c.plaid:
        ok = config.settings.plaid_configured() and plaid.remove_item(user_id, c.plaid.access_token)
        removed["bank_connection"] = ("removed at Plaid" if ok else
                                      "forgotten here; Plaid didn't confirm removing the item")
    removed |= {"subscriptions": len(u.subscriptions), "findings": len(u.findings), "emails": len(u.emails),
                "transactions": len(u.transactions), "alerts": alerts.count(user_id)}
    with db.tx() as t:
        t.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        t.execute("DELETE FROM connections WHERE user_id = ?", (user_id,))
        t.execute("DELETE FROM alerts WHERE user_id = ?", (user_id,))
        t.execute("DELETE FROM users WHERE id = ?", (user_id,))
    budget.forget_user(user_id)
    nylas.forget_states(user_id)
    store.forget(user_id)
    if user_id == SINGLE_USER:
        global _single_ready
        with _single_lock:
            _single_ready = False
    return {"ok": True, "removed": removed}


def prune(now: datetime | None = None) -> dict:
    """Delete visitor sessions idle for CLAWBACK_SESSION_IDLE_DAYS, connections included (see the module notes)."""
    now = now or db.now()
    cutoff = db.iso(now - timedelta(days=config.settings.session_idle_days))
    idle = [r["id"] for r in db.query("SELECT id FROM users WHERE kind = 'visitor' AND last_seen < ?", (cutoff,))]
    connected = 0
    for user_id in idle:
        connected += int(connections.get(user_id).any())
        delete(user_id)
    with db.tx() as t:
        orphans = t.execute("DELETE FROM sessions WHERE user_id NOT IN (SELECT id FROM users)").rowcount
        t.execute("DELETE FROM session_log WHERE at < ?", (db.iso(now - timedelta(days=1)),))
    budget.prune()
    return {"sessions": len(idle), "with_connections": connected, "orphan_sessions": orphans}


def reset() -> None:
    """Forget process state (tests)."""
    global _single_ready
    with _single_lock:
        _single_ready = False
    with _locks_guard:
        _locks.clear()
