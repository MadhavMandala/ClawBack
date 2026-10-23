"""Storage.

MISSING [database]: this is an in-memory store. Everything resets when the server restarts, and there is
only one user ("demo"). Replace it with Supabase Postgres plus row-level security. The interface below is
what the rest of the code depends on, so swapping the backend shouldn't touch the pipeline.

Saved Gmail / Plaid connections are the one thing that survives a restart: see connections.py.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from .models import Email, Finding, Subscription, TraceStep, Transaction


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


class MemoryStore:
    def __init__(self) -> None:
        self._users: dict[str, UserData] = defaultdict(UserData)

    def user(self, user_id: str) -> UserData:
        return self._users[user_id]

    def reset(self, user_id: str) -> UserData:
        self._users[user_id] = UserData()
        return self._users[user_id]

    def use_real_data(self, user_id: str) -> UserData:
        """Leave demo mode: drop the seeded data and everything derived from it. Uploaded statements stay.

        Demo trace rows go on the next pipeline run (pipeline/run.py keeps only Gmail / Plaid rows).
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
        return u


store = MemoryStore()
