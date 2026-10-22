"""Storage.

MISSING [database]: this is an in-memory store. Everything resets when the server restarts, and there is
only one user ("demo"). Replace it with Supabase Postgres plus row-level security. The interface below is
what the rest of the code depends on, so swapping the backend shouldn't touch the pipeline.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from .models import Email, Fact, Subscription, TraceStep, Transaction


@dataclass
class UserData:
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
    # Extracted facts by email id, so each email goes to a model once. Reset demo clears it.
    facts: dict[str, Fact] = field(default_factory=dict)


class MemoryStore:
    def __init__(self) -> None:
        self._users: dict[str, UserData] = defaultdict(UserData)

    def user(self, user_id: str) -> UserData:
        return self._users[user_id]

    def reset(self, user_id: str) -> UserData:
        self._users[user_id] = UserData()
        return self._users[user_id]


store = MemoryStore()
