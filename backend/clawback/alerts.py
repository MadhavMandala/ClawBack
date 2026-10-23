"""In-app alerts: what background work (the nightly job, webhooks) found that the user hasn't seen yet.

No email or push. The dashboard reads GET /api/alerts and marks them seen with POST /api/alerts/seen.

An alert is a flag (not "info") on a subscription or bill, or an open finding, that appeared during a background
run: keys() is taken before and after the run, and only keys that are new get an alert. Each key alerts once
per user (UNIQUE (user_id, key)), so running the nightly job twice, or a webhook delivered twice, adds nothing.
Stored in the `alerts` table (db.py); titles and messages are the app's own text, never email content.
"""

from __future__ import annotations

from . import db
from .store import UserData

KEEP = 200  # newest alerts kept per user


def keys(u: UserData) -> dict[str, dict]:
    """Everything in this user's data that would deserve an alert, by a stable key."""
    out: dict[str, dict] = {}
    for s in u.subscriptions.values():
        if s.status == "kept":
            continue
        for f in s.flags:
            if f.severity == "info":
                continue
            out[f"flag:{s.id}:{f.kind}"] = {"kind": "flag", "ref": s.id, "title": s.merchant,
                                             "message": f.message, "amount": round(f.monthly_savings, 2)}
    for f in u.findings.values():
        if f.status == "open":
            out[f"finding:{f.id}"] = {"kind": "finding", "ref": f.id, "title": f.title, "message": f.message,
                                      "amount": round(f.amount, 2)}
    return out


def record_new(user_id: str, before: set[str], u: UserData) -> int:
    """Add an alert for each key in `u` that wasn't in `before`. Returns how many were new."""
    new = {k: v for k, v in keys(u).items() if k not in before}
    if not new:
        return 0
    added = 0
    stamp = db.iso(db.now())
    with db.tx() as c:
        for key, a in new.items():
            added += c.execute(
                "INSERT OR IGNORE INTO alerts (user_id, key, kind, ref, title, message, amount, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, key, a["kind"], a["ref"], a["title"][:200], a["message"][:500], a["amount"], stamp),
            ).rowcount
        c.execute("DELETE FROM alerts WHERE user_id = ? AND id NOT IN "
                  "(SELECT id FROM alerts WHERE user_id = ? ORDER BY id DESC LIMIT ?)", (user_id, user_id, KEEP))
    return added


def list_for(user_id: str, limit: int = 50) -> dict:
    rows = db.query("SELECT id, kind, ref, title, message, amount, created_at, seen_at FROM alerts "
                    "WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
    return {
        "alerts": [{"id": r["id"], "kind": r["kind"], "ref": r["ref"], "title": r["title"], "message": r["message"],
                    "amount": r["amount"], "created_at": r["created_at"], "seen": r["seen_at"] is not None}
                   for r in rows],
        "unseen": unseen(user_id),
    }


def unseen(user_id: str) -> int:
    row = db.one("SELECT COUNT(*) AS n FROM alerts WHERE user_id = ? AND seen_at IS NULL", (user_id,))
    return int(row["n"]) if row else 0


def mark_seen(user_id: str, ids: list[int] | None = None) -> int:
    """Mark these alerts (all when ids is None) as seen. Returns how many changed."""
    stamp = db.iso(db.now())
    if ids is None:
        return db.execute("UPDATE alerts SET seen_at = ? WHERE user_id = ? AND seen_at IS NULL", (stamp, user_id))
    changed = 0
    with db.tx() as c:
        for i in ids:
            changed += c.execute("UPDATE alerts SET seen_at = ? WHERE user_id = ? AND id = ? AND seen_at IS NULL",
                                 (stamp, user_id, int(i))).rowcount
    return changed


def count(user_id: str) -> int:
    row = db.one("SELECT COUNT(*) AS n FROM alerts WHERE user_id = ?", (user_id,))
    return int(row["n"]) if row else 0


def delete_user(user_id: str) -> int:
    return db.execute("DELETE FROM alerts WHERE user_id = ?", (user_id,))
