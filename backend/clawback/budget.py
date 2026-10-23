"""Daily model spend caps, so a public demo can't run up the Token Factory bill.

llm.chat() calls blocked() before every model call and add() after it. Spend is kept per user per UTC day in the
database `spend` table, so the nightly job (a second process) counts too. Two caps, both settings:
  CLAWBACK_SESSION_DAILY_USD (default 0.25) per user; system users (ids starting "_", such as the shared demo
  template) are exempt from it.
  CLAWBACK_GLOBAL_DAILY_USD (default 5.00) for everyone together.
0 or less turns a cap off. Calls already in flight when a cap is reached still finish, so a cap can be passed by a
few calls' worth of cents. When a cap is hit, the caller gets llm.BudgetExceeded and takes its non-model fallback.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import config, db

LIMIT_NOTE = "daily model limit reached"
KEEP_DAYS = 35
DELETED = "_deleted"  # spend of deleted users is kept under this id, so the global total stays right


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def spent(user_id: str, day: str | None = None) -> float:
    row = db.one("SELECT usd FROM spend WHERE day = ? AND user_id = ?", (day or today(), user_id))
    return float(row["usd"]) if row else 0.0


def spent_all(day: str | None = None) -> float:
    row = db.one("SELECT COALESCE(SUM(usd), 0) AS usd FROM spend WHERE day = ?", (day or today(),))
    return float(row["usd"]) if row else 0.0


def blocked(user_id: str) -> str | None:
    """Why a model call for this user must not be made today, or None when it may."""
    s = config.settings
    if s.global_daily_usd > 0 and spent_all() >= s.global_daily_usd:
        return f"{LIMIT_NOTE} (all users, ${s.global_daily_usd:.2f})"
    if s.session_daily_usd > 0 and not user_id.startswith("_") and spent(user_id) >= s.session_daily_usd:
        return f"{LIMIT_NOTE} (${s.session_daily_usd:.2f} per session)"
    return None


def add(user_id: str, usd: float) -> None:
    db.execute(
        "INSERT INTO spend (day, user_id, usd, calls) VALUES (?, ?, ?, 1) "
        "ON CONFLICT (day, user_id) DO UPDATE SET usd = usd + excluded.usd, calls = calls + 1",
        (today(), user_id, max(0.0, float(usd))),
    )


def forget_user(user_id: str) -> None:
    """On delete: fold the user's spend into DELETED, so nothing ties it to them but the daily total is kept."""
    with db.tx() as c:
        for row in c.execute("SELECT day, usd, calls FROM spend WHERE user_id = ?", (user_id,)).fetchall():
            c.execute(
                "INSERT INTO spend (day, user_id, usd, calls) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (day, user_id) DO UPDATE SET usd = usd + excluded.usd, calls = calls + excluded.calls",
                (row["day"], DELETED, row["usd"], row["calls"]),
            )
        c.execute("DELETE FROM spend WHERE user_id = ?", (user_id,))


def prune() -> int:
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=KEEP_DAYS)).isoformat()
    return db.execute("DELETE FROM spend WHERE day < ?", (cutoff,))
