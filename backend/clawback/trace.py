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


# Steps that run when the user clicks something. They survive pipeline re-runs so the dashboard can show them.
ON_CLICK_STAGES = frozenset({"alternatives", "alternatives_plans", "cancel_lookup", "cancel_email"})
MAX_ON_CLICK_ROWS = 20


def start_run(user_id: str) -> None:
    """Drop the previous pipeline run's rows; keep the newest on-click rows."""
    trace = store.user(user_id).trace
    kept = [s for s in trace if s.stage in ON_CLICK_STAGES][-MAX_ON_CLICK_ROWS:]
    trace[:] = kept


def view(user_id: str) -> list[TraceStep]:
    """Pipeline rows in run order, then on-click rows newest first."""
    trace = store.user(user_id).trace
    pipeline = [s for s in trace if s.stage not in ON_CLICK_STAGES]
    clicks = [s for s in trace if s.stage in ON_CLICK_STAGES]
    return pipeline + clicks[::-1]


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
