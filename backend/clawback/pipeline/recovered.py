"""History of money recovered (recovered-history): a dated list, with confirmed and self-reported money apart.

Events:
  - cancelled_subscription (confirmed): a cancellation pipeline/confirm.py confirmed from bank data. `monthly` is what
    it no longer costs each month; `amount` is the charges that didn't come so far.
  - refund (confirmed): a bank credit that matched a finding the user marked done (refund, reversal, payout).
  - self_reported: the amount the user typed when marking a finding done, while no matching credit has shown up.
    Once a credit matches, the confirmed refund replaces it, so nothing is counted twice.

Confirmed events are kept in UserData.recovered and stay when old transactions roll out of the bank's window.
Self-reported events are built from UserData.got_back each time, so they always match what the user last said.

Totals: `confirmed` is one-time money back seen in the bank; `self_reported` is what the user reported and the bank
doesn't show yet; cancellations are counted apart, per month (`cancelled_monthly`) and so far (`cancelled_saved`).
summary()["recovered_total"] is confirmed + self-reported, and recovered_note says how much of it is confirmed.
"""

from __future__ import annotations

from datetime import date

from ..findings.util import money
from ..models import RecoveryEvent
from ..store import UserData, store

SELF_NOTE = "You marked this done and said it came back. ClawBack hasn't seen the credit in your bank yet."


def self_reported(u: UserData, today: date | None = None) -> list[RecoveryEvent]:
    out = []
    for fid, amount in u.got_back.items():
        if amount <= 0 or u.finding_status.get(fid) != "done" or f"refund:{fid}" in u.recovered:
            continue
        f, w = u.findings.get(fid), u.refund_watch.get(fid)
        out.append(RecoveryEvent(
            id=f"self:{fid}", kind="self_reported", status="self_reported",
            on=u.done_on.get(fid) or (w.done_on if w else None) or today or date.today(),
            merchant=(f.merchant if f else w.merchant if w else ""), amount=round(amount, 2), note=SELF_NOTE,
            finding_id=fid))
    return out


def events(u: UserData) -> list[RecoveryEvent]:
    """Newest first."""
    return sorted([*u.recovered.values(), *self_reported(u)], key=lambda e: (e.on, e.id), reverse=True)


def totals(u: UserData) -> dict:
    evs = events(u)
    cancelled = [e for e in evs if e.kind == "cancelled_subscription"]
    return {
        "confirmed": round(sum(e.amount for e in evs if e.kind == "refund" and e.status == "confirmed"), 2),
        "self_reported": round(sum(e.amount for e in evs if e.status == "self_reported"), 2),
        "cancelled_monthly": round(sum(e.monthly for e in cancelled), 2),
        "cancelled_saved": round(sum(e.amount for e in cancelled), 2),
        "cancelled_count": len(cancelled),
    }


def note(t: dict) -> str:
    parts = []
    if t["confirmed"]:
        parts.append(f"Confirmed in your bank data: {money(t['confirmed'])} in refunds and credits.")
    if t["self_reported"]:
        parts.append(f"Self-reported: {money(t['self_reported'])} you marked as got back, not seen in your bank yet.")
    if t["cancelled_monthly"]:
        n = t["cancelled_count"]
        parts.append(f"{n} cancellation{'s' if n != 1 else ''} confirmed: {money(t['cancelled_monthly'])} a month "
                     f"you no longer pay ({money(t['cancelled_saved'])} so far).")
    return " ".join(parts) or ("Nothing recovered yet. When you mark a finding done or cancel a subscription, "
                               "ClawBack checks your bank that the money came back.")


def history(user_id: str) -> dict:
    """GET /api/recovered."""
    u = store.user(user_id)
    t = totals(u)
    return {"totals": t, "note": note(t), "events": [e.model_dump(mode="json") for e in events(u)]}
