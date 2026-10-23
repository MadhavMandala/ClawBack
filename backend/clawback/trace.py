"""Per-step log of which engine did what, how long it took, and what it cost.

The judges asked to see "which model is doing what", so every pipeline step records itself here
and the dashboard shows the list.

Rows from outside data sources (engines in SOURCE_ENGINES) survive a pipeline re-run and are replaced on the
next sync of that source. Notes never contain tokens, secrets or email bodies.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime, timezone

from .models import TraceStep
from .store import store

SOURCE_ENGINES = ("nylas", "plaid")


def record(user_id: str, stage: str, engine: str, status: str = "ok", **kw) -> TraceStep:
    step = TraceStep(at=datetime.now(timezone.utc), stage=stage, engine=engine, status=status, **kw)
    store.user(user_id).trace.append(step)
    return step


def drop(user_id: str, engines: tuple[str, ...]) -> None:
    u = store.user(user_id)
    u.trace = [t for t in u.trace if t.engine not in engines]


def keep_only_sources(user_id: str) -> None:
    """Called at the start of a pipeline run: pipeline rows are rebuilt, source rows stay."""
    u = store.user(user_id)
    u.trace = [t for t in u.trace if t.engine in SOURCE_ENGINES]


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
