"""The nightly job:  python -m clawback.nightly

For every user with a saved email or bank connection:
  1. grant check: GET /v3/grants/{id} at Nylas; a grant that is gone or invalid is marked needs_reconnect;
  2. sync: read the mail again (180 days) and pull new bank transactions from the saved Plaid cursor;
  3. re-run the pipeline, which re-runs the price checks for refundable purchases;
  4. record an in-app alert for each flag or finding that is new since the last run (alerts.py).
Then it deletes visitor sessions idle for CLAWBACK_SESSION_IDLE_DAYS, connections included (sessions.prune).

Safe to run twice: syncs are incremental, and each alert is recorded once per user. Safe if one user fails:
each user runs on its own, and a failure is counted, logged by type only, and the others carry on. It can run
while the API is up: each user is saved only if the API didn't change that user meanwhile (otherwise it is
loaded again and redone once), and the API reloads users this job changed.

Prints one summary line. Exit code 0 when every user went through, 1 when any failed, 2 when the job itself
couldn't run (for example, the database couldn't be opened).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from . import connect, connections, db, sessions
from .store import SaveConflict, store

log = logging.getLogger("clawback.nightly")


def refresh_user(user_id: str) -> dict:
    """One user, retried once from a fresh load if the API saved the same user while this ran."""
    for attempt in (1, 2):
        store.forget(user_id)  # always start from what is on disk
        result = connect.nightly_refresh(user_id)
        try:
            store.save(user_id, careful=True)
            return result
        except SaveConflict:
            if attempt == 2:
                raise
    return {}


def run(prune: bool = True, only: list[str] | None = None) -> tuple[int, str]:
    start = time.perf_counter()
    db.connection()
    users = [u for u in sessions_with_connections() if not only or u in only]
    ok = failed = alerts = reconnect = skipped = 0
    for user_id in users:
        try:
            result = refresh_user(user_id)
            ok += 1
            alerts += result.get("alerts", 0)
            reconnect += int(result.get("grant") in ("gone", "invalid"))
            skipped += int(result.get("mode") == "real" and not result.get("rerun"))
        except Exception as exc:
            failed += 1
            log.error("nightly: a user failed (%s)", type(exc).__name__)
        finally:
            store.forget(user_id)
    pruned = sessions.prune() if prune else {"sessions": 0}
    db.set_meta("nightly_last_run", db.iso(db.now()))
    line = (f"nightly: {ok} users refreshed, {failed} failed, {alerts} new alerts, {reconnect} need a new email "
            f"sign-in, {skipped} not re-run (mail unreadable), {pruned['sessions']} idle sessions deleted "
            f"in {time.perf_counter() - start:.1f}s")
    return (1 if failed else 0), line


def sessions_with_connections() -> list[str]:
    """Users with a saved connection and a user row (a connection without a user is skipped)."""
    known = {r["id"] for r in db.query("SELECT id FROM users")}
    return [u for u in connections.users_with_connections() if u in known]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m clawback.nightly", description=__doc__.split("\n")[0])
    parser.add_argument("--no-prune", action="store_true", help="don't delete idle sessions")
    parser.add_argument("--user", action="append", help="only this user id (repeatable)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        code, line = run(prune=not args.no_prune, only=args.user)
    except Exception as exc:
        print(f"nightly: could not run ({type(exc).__name__}: {str(exc)[:200]})")
        return 2
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
