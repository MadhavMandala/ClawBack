"""Demo data for a user: the fake bank history and inbox from demo_data, run through the pipeline.

Every visitor gets the same demo, so it is built once per day (and per "models on or off") under the system
user TEMPLATE_USER, and each seed() copies it. A new session is then instant, and the demo's model calls
(extraction of the demo emails) are paid once a day, not once per visitor. The copy carries the template's trace,
so each visitor still sees which model did what.
"""

from __future__ import annotations

import copy
import threading
from datetime import date

from . import demo_data, llm
from .findings import rulebook
from .pipeline.run import run, summary
from .store import UserData, store

TEMPLATE_USER = "_demo"  # "_" ids are system users: never a session, exempt from the per-session model cap

_lock = threading.Lock()
_template: tuple[tuple, UserData] | None = None


def _build(today: date) -> UserData:
    u = store.reset(TEMPLATE_USER)
    u.transactions = demo_data.transactions(today)
    u.emails = demo_data.emails(today)
    book = rulebook.current()
    if book:
        u.emails += demo_data.settlement_story(today, u.transactions, u.emails, book)
    demo_data.decisions(u, today)  # what the demo user already did: one cancellation, started weeks ago
    run(TEMPLATE_USER, today)
    data = store.user(TEMPLATE_USER)
    store.forget(TEMPLATE_USER)
    return data


def template(today: date) -> UserData:
    global _template
    key = (today, llm.available())
    with _lock:
        if _template is None or _template[0] != key:
            _template = (key, _build(today))
        return _template[1]


def seed(user_id: str, today: date | None = None) -> dict:
    """Switch this user to demo mode with fresh demo data. Saved connections stay saved but unused."""
    state = store.user(user_id).state  # a setting, not data: it survives reseeding
    data = copy.deepcopy(template(today or date.today()))
    data.state = state
    store.replace(user_id, data)
    return summary(user_id)


def clear() -> None:
    """Forget the template (tests, or after the demo data changed)."""
    global _template
    with _lock:
        _template = None
