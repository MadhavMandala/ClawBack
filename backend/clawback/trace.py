"""Per-step log of which engine did what, how long it took, and what it cost.

The judges asked to see "which model is doing what", so every pipeline step records itself here
and the dashboard shows the list.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime, timezone

from .models import TraceStep
from .store import store


def record(user_id: str, stage: str, engine: str, status: str = "ok", **kw) -> TraceStep:
    step = TraceStep(at=datetime.now(timezone.utc), stage=stage, engine=engine, status=status, **kw)
    store.user(user_id).trace.append(step)
    return step


@contextmanager
def timed(user_id: str, stage: str, engine: str, note: str = ""):
    """Record a code-only step with its run time."""
    start = time.perf_counter()
    info: dict = {"note": note}
    try:
        yield info
    finally:
        record(user_id, stage, engine, ms=(time.perf_counter() - start) * 1000, note=info.get("note", note))
