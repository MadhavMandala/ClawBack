"""Storage: each user's UserData, kept in memory and written to the database (db.py) after each change.

The rest of the code only uses `store.user(user_id)` and mutates the UserData it returns. The API saves the
user at the end of every request (sessions.user_scope); background work (webhooks, the nightly job) saves
explicitly. A save is skipped when nothing changed, and only updates a user row that exists: rows are created
when a session is created (sessions.py) or, in single-user mode, at startup. So a deleted user can't come back.

What goes to disk
  Every UserData field, generically: `serialize()` turns the dataclass into JSON (dates, datetimes, enums,
  tuples, pydantic models, including fields a model excludes from the API such as Finding.details), and
  `deserialize()` validates each field back against its type hint with pydantic. A new field persists with no
  change here, as long as pydantic can validate it (dates, datetimes, str/int/float/bool, lists and dicts of
  those, pydantic models) and it has a default. A field that no longer validates falls back to its default
  (logged), so one bad field never loses a whole session. A defaultdict default is restored as a defaultdict.
  The JSON is encrypted (crypto.py) before it is written.

Email bodies never touch the disk
  Only demo emails (source "demo") are written: they are fake and come from demo_data. Every other email
  (mail read through Nylas, or any future source) is dropped from the saved copy, with its body; extracted facts
  (`facts`, keyed by email id) and everything derived from them are saved. Several pipeline steps read the
  bodies again on each run (triage, the extract rules, purchases, flights, bill promos, settlements), so a
  real-mode user loaded from disk is "cold": connect.ensure_fresh() reads the mail again from Nylas before the
  first request uses it, and the nightly job always re-reads it.

Two processes
  The nightly job (a separate process, python -m clawback.nightly) writes the same file. Each row has a version,
  and every save is conditional on it, so a stale copy never overwrites a newer one. The API calls refresh() at
  the start of each request and reloads a user whose row the job changed. If the job saves a user while one of
  that user's requests runs, the API's save merges field by field (see save()). The job saves with careful=True
  and redoes the user from disk when the API saved first.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import threading
import time
import typing
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from pydantic import BaseModel, TypeAdapter
from pydantic_core import to_jsonable_python

from . import crypto, db
from .models import Email, Fact, Finding, Subscription, TraceStep, Transaction

log = logging.getLogger("clawback.store")

PERSISTED_EMAIL_SOURCES = frozenset({"demo"})  # fake demo mail; everything else stays in memory only


@dataclass
class UserData:
    # "demo" = seeded fake data. "real" = data from the user's own connections. The two never mix.
    mode: str = "demo"
    transactions: list[Transaction] = field(default_factory=list)
    emails: list[Email] = field(default_factory=list)
    subscriptions: dict[str, Subscription] = field(default_factory=dict)
    # What the user told us: subscription id -> list of (date, used?)
    checkins: dict[str, list[tuple[date, bool]]] = field(default_factory=lambda: defaultdict(list))
    # Subscriptions the user chose to keep: id -> date decided (suppresses nagging for 90 days)
    kept: dict[str, date] = field(default_factory=dict)
    # Subscriptions the user started cancelling: id -> date. MISSING [cancel-confirmation]: never confirmed.
    cancel_pending: dict[str, date] = field(default_factory=dict)
    trace: list[TraceStep] = field(default_factory=list)
    # One-time money (duplicate charges, fees, refunds, settlements), rebuilt by each pipeline run.
    findings: dict[str, Finding] = field(default_factory=dict)
    # What the user decided about a finding: id -> dismissed | done. Survives re-runs (ids are stable).
    finding_status: dict[str, str] = field(default_factory=dict)
    # Self-reported money back per finding marked done. MISSING [cancel-confirmation]: not checked against the bank.
    got_back: dict[str, float] = field(default_factory=dict)
    # Per bill: its rules/bills.json entry and its charge amounts (oldest first), for the negotiation script.
    bill_info: dict[str, dict] = field(default_factory=dict)
    # Plaid /transactions/sync position of the transactions held in memory. None = pull from the start.
    plaid_cursor: str | None = None
    # Extracted facts by email id, so each email goes to a model once. Reset demo clears it.
    facts: dict[str, Fact] = field(default_factory=dict)


# --- Serialization ---------------------------------------------------------------------------------

def _plain(value):
    """JSON-ready form of a value. Unlike pydantic's dump, keeps fields a model marks exclude=True."""
    if isinstance(value, BaseModel):
        return {name: _plain(getattr(value, name)) for name in type(value).model_fields}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k.value if isinstance(k, Enum) else k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return to_jsonable_python(value)  # dates, datetimes, enums, UUIDs, decimals...


def serialize(u: UserData) -> dict:
    data = {f.name: _plain(getattr(u, f.name)) for f in dataclasses.fields(UserData)}
    data["emails"] = [e for e, src in zip(data["emails"], (m.source for m in u.emails))
                      if src in PERSISTED_EMAIL_SOURCES]
    return data


def _parts(u: UserData) -> dict[str, str]:
    """Each field as canonical JSON: what is compared to see what changed, and what is written."""
    return {k: json.dumps(v, separators=(",", ":"), sort_keys=True) for k, v in serialize(u).items()}


def _text(parts: dict[str, str]) -> str:
    return "{" + ",".join(f"{json.dumps(k)}:{v}" for k, v in sorted(parts.items())) + "}"


_hints: dict[str, object] | None = None
_adapters: dict[str, TypeAdapter] = {}


def _adapter(name: str) -> TypeAdapter:
    global _hints
    if _hints is None:
        _hints = typing.get_type_hints(UserData)
    if name not in _adapters:
        _adapters[name] = TypeAdapter(_hints[name])
    return _adapters[name]


def deserialize(data: dict) -> UserData:
    u = UserData()
    for f in dataclasses.fields(UserData):
        if f.name not in data:
            continue
        try:
            value = _adapter(f.name).validate_python(data[f.name])
        except Exception as exc:
            log.warning("stored field %r no longer validates (%s); using its default", f.name, type(exc).__name__)
            continue
        default = getattr(u, f.name)
        if isinstance(default, defaultdict) and not isinstance(value, defaultdict):
            value = defaultdict(default.default_factory, value)
        setattr(u, f.name, value)
    return u


# --- The store -------------------------------------------------------------------------------------

class SaveConflict(Exception):
    """Another process saved this user after this copy was loaded."""


@dataclass
class _Entry:
    data: UserData
    version: int = 0  # the row version this copy was loaded from or last saved as
    base: dict[str, str] = field(default_factory=dict)  # each field's JSON as last loaded or saved
    cold: bool = False  # loaded from disk in real mode: real emails must be read again before use
    retry_at: float = 0.0  # while cold after a failed read: when to try reading the mail again
    used: float = field(default_factory=time.monotonic)  # last store.user() call, for evicting idle users


MAX_IN_MEMORY = 300  # users kept in memory; past this, users idle for EVICT_AFTER_S are saved and dropped
EVICT_AFTER_S = 600.0


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._users: dict[str, _Entry] = {}

    # The interface the pipeline uses.

    def user(self, user_id: str) -> UserData:
        with self._lock:
            entry = self._users.get(user_id)
            if entry is None:
                self._evict_idle()
                entry = self._users[user_id] = self._load(user_id) or _Entry(UserData())
            entry.used = time.monotonic()
            return entry.data

    def _evict_idle(self) -> None:
        """Keep memory bounded on a public demo. A user idle for 10 minutes has no request or background work
        running (each touches its user constantly), so it is saved and dropped; it loads again on next use."""
        if len(self._users) < MAX_IN_MEMORY:
            return
        cutoff = time.monotonic() - EVICT_AFTER_S
        for user_id in sorted((u for u, e in self._users.items() if e.used < cutoff), key=lambda u: self._users[u].used):
            if len(self._users) < MAX_IN_MEMORY:
                break
            try:
                self.save(user_id)
            except Exception as exc:  # keep it rather than lose a change
                log.warning("could not save an idle user before dropping it (%s)", type(exc).__name__)
                continue
            self._users.pop(user_id, None)

    def reset(self, user_id: str) -> UserData:
        return self.replace(user_id, UserData())

    def replace(self, user_id: str, data: UserData) -> UserData:
        with self._lock:
            old = self._users.get(user_id)
            self._users[user_id] = _Entry(data, version=old.version if old else self._row_version(user_id) or 0,
                                          base=old.base if old else {})
            return data

    def use_real_data(self, user_id: str) -> UserData:
        """Leave demo mode: drop the seeded data and everything derived from it. Uploaded statements stay.

        Demo trace rows go too; Nylas / Plaid rows stay. Cached email facts stay: they are keyed by email id,
        and demo emails are gone.
        """
        u = self.user(user_id)
        if u.mode != "real":
            u.mode = "real"
            u.transactions = [t for t in u.transactions if t.source != "demo"]
            u.emails = [e for e in u.emails if e.source != "demo"]
            u.subscriptions = {}
            u.checkins = defaultdict(list)
            u.kept = {}
            u.cancel_pending = {}
            u.findings, u.finding_status, u.got_back = {}, {}, {}
            u.plaid_cursor = None
            u.trace = [t for t in u.trace if t.engine in ("nylas", "plaid")]  # trace.SOURCE_ENGINES (no import: cycle)
        return u

    # Persistence.

    def save(self, user_id: str, careful: bool = False) -> bool:
        """Write the user if it changed. Only updates an existing row. Returns True when a row was written.

        A save only succeeds if the row is still at the version this copy was loaded from, so a stale copy never
        overwrites another process's write. On a conflict:
          careful=True (the nightly job): raise SaveConflict; the job loads the user again and redoes it.
          otherwise (the API): a three-way merge. Fields this copy changed since it was loaded keep this copy's
          value; every other field takes the newer value on disk; then it saves again. So a click saved during
          a nightly run keeps both the click and the night's new data (derived results are rebuilt on the next
          pipeline run).
        """
        for attempt in (1, 2):
            with self._lock:
                entry = self._users.get(user_id)
                if entry is None:
                    return False
                parts = _parts(entry.data)
                if parts == entry.base:
                    return False
                version = entry.version
            blob = crypto.encrypt(_text(parts).encode())  # outside the lock: other users don't wait for this
            with db.tx() as c:
                changed = c.execute("UPDATE users SET data = ?, version = version + 1 WHERE id = ? AND version = ?",
                                    (blob, user_id, version)).rowcount
                row = c.execute("SELECT version FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:  # deleted, or never created: nothing to save
                return False
            with self._lock:
                if changed:
                    if self._users.get(user_id) is entry:
                        entry.version, entry.base = row[0], parts
                    return True
                if careful:
                    raise SaveConflict(user_id)
                if attempt == 1 and self._merge_into_disk_copy(user_id, entry, parts):
                    continue
                log.warning("a user changed on disk during this request and could not be merged; kept the disk copy")
                self._users[user_id] = self._load(user_id) or _Entry(UserData())
                return False
        return False

    def _merge_into_disk_copy(self, user_id: str, mine: _Entry, parts: dict[str, str]) -> bool:
        disk = self._load(user_id)
        if disk is None:
            return False
        for name, text in parts.items():
            if text != mine.base.get(name):  # this copy changed it
                setattr(disk.data, name, getattr(mine.data, name))
        # Mail that is never written stays as this process has it.
        disk.data.emails = ([e for e in disk.data.emails if e.source in PERSISTED_EMAIL_SOURCES]
                            + [e for e in mine.data.emails if e.source not in PERSISTED_EMAIL_SOURCES])
        disk.cold = mine.cold
        self._users[user_id] = disk
        log.warning("a user changed on disk during this request; merged the two copies")
        return True

    def refresh(self, user_id: str) -> None:
        """Reload the user if another process (the nightly job) saved a newer version."""
        with self._lock:
            entry = self._users.get(user_id)
            if entry is None:
                return
            version = self._row_version(user_id)
            if version is not None and version > entry.version:
                fresh = self._load(user_id)
                if fresh is not None:
                    self._users[user_id] = fresh

    def is_cold(self, user_id: str) -> bool:
        with self._lock:
            entry = self._users.get(user_id)
            return bool(entry and entry.cold)

    def mark_warm(self, user_id: str) -> None:
        with self._lock:
            if entry := self._users.get(user_id):
                entry.cold = False

    def retry_due(self, user_id: str) -> bool:
        with self._lock:
            entry = self._users.get(user_id)
            return entry is None or time.monotonic() >= entry.retry_at

    def retry_later(self, user_id: str, seconds: float) -> None:
        with self._lock:
            if entry := self._users.get(user_id):
                entry.retry_at = time.monotonic() + seconds

    def version(self, user_id: str) -> int:
        with self._lock:
            entry = self._users.get(user_id)
            return entry.version if entry else 0

    def forget(self, user_id: str) -> None:
        """Drop the in-memory copy (after the user's rows were deleted, or to force a reload)."""
        with self._lock:
            self._users.pop(user_id, None)

    def clear(self) -> None:
        with self._lock:
            self._users.clear()

    def _row_version(self, user_id: str) -> int | None:
        row = db.one("SELECT version FROM users WHERE id = ?", (user_id,))
        return row["version"] if row else None

    def _load(self, user_id: str) -> _Entry | None:
        row = db.one("SELECT version, data FROM users WHERE id = ?", (user_id,))
        if row is None or row["data"] is None:
            return _Entry(UserData(), version=row["version"]) if row else None
        try:
            text = crypto.decrypt(row["data"]).decode()
            data = deserialize(json.loads(text))
        except (crypto.CryptoError, ValueError) as exc:
            log.warning("stored data for a user could not be read (%s); starting it empty", exc)
            return _Entry(UserData(), version=row["version"])
        return _Entry(data, version=row["version"], base=_parts(data), cold=data.mode == "real")


store = Store()
