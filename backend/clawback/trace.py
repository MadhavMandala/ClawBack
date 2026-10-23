"""Per-step log of which engine did what, how long it took, and what it cost.

The judges asked to see "which model is doing what", so every pipeline step records itself here
and the dashboard shows the list.

A pipeline re-run rebuilds its own rows. Two kinds survive it: rows from outside data sources (engines in
SOURCE_ENGINES), which are replaced on the next sync of that source, and rows from on-click steps
(ON_CLICK_STAGES), newest MAX_ON_CLICK_ROWS kept. Notes never contain tokens, secrets or email bodies.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime, timezone

from .models import TraceStep
from .store import store

SOURCE_ENGINES = ("nylas", "plaid")

# Steps that run when the user clicks something. They survive pipeline re-runs so the dashboard can show them.
ON_CLICK_STAGES = frozenset({"alternatives", "alternatives_plans", "cancel_lookup", "cancel_email", "bill offers",
                             "letter"})
MAX_ON_CLICK_ROWS = 20


def start_run(user_id: str) -> None:
    """Called at the start of a pipeline run: drop the last run's rows, keep source rows and the newest on-click rows."""
    trace = store.user(user_id).trace
    clicks = {id(s) for s in [s for s in trace if s.stage in ON_CLICK_STAGES][-MAX_ON_CLICK_ROWS:]}
    trace[:] = [s for s in trace if s.engine in SOURCE_ENGINES or id(s) in clicks]


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


def drop(user_id: str, engines: tuple[str, ...]) -> None:
    trace = store.user(user_id).trace
    trace[:] = [t for t in trace if t.engine not in engines]


@contextmanager
def timed(user_id: str, stage: str, engine: str, note: str = ""):
    """Record a step with its run time. If the block raises, the row is marked "error" and the error re-raised.

    Only exceptions with a `safe_message` (see sources/net.py) put their text in the note; others give their type.
    """
    start = time.perf_counter()
    info: dict = {"note": note}
    status = "ok"
    try:
        yield info
    except Exception as exc:
        status = "error"
        reason = getattr(exc, "safe_message", None) or type(exc).__name__
        info["note"] = f"{info.get('note') or note} failed: {reason}".strip()
        raise
    finally:
        record(user_id, stage, engine, status=status, ms=(time.perf_counter() - start) * 1000,
               note=info.get("note", note))
