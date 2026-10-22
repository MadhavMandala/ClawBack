"""Run the whole pipeline for one user and store the results."""

from __future__ import annotations

import re
from datetime import date

from ..merchants import by_name
from ..models import Cadence, Subscription
from ..store import store
from ..trace import start_run, timed
from .extract import extract_all
from .flags import flag_one, flag_overlaps
from .recurring import detect, resolve_store_billed
from .triage import triage
from .usage import signals_for, summarize
from .value import membership_value


def run(user_id: str, today: date | None = None) -> dict:
    today = today or date.today()
    u = store.user(user_id)
    start_run(user_id)

    candidates = triage(user_id, u.emails)
    facts = extract_all(user_id, candidates)

    with timed(user_id, "recurring", "code") as info:
        subs = detect(u.transactions, today)
        resolve_store_billed(subs, [(f.merchant, f.amount) for f in facts if f.kind == "store_receipt"])
        info["note"] = f"{len(u.transactions)} transactions -> {len(subs)} recurring charges"

    # Email-only: free trials that haven't charged yet.
    known = {s.merchant for s in subs}
    for f in facts:
        if f.kind == "trial" and f.trial_end and f.trial_end >= today and f.merchant and f.merchant not in known:
            m = by_name(f.merchant)
            subs.append(Subscription(
                id=re.sub(r"[^a-z0-9]+", "-", f.merchant.lower()).strip("-"),
                merchant=f.merchant,
                category=m.category if m else "unknown",
                cadence=Cadence.monthly,
                amount=f.amount,
                monthly_cost=f.amount or 0.0,
                next_expected=f.trial_end,
                status="trial",
                detected_from=["email"],
            ))
            known.add(f.merchant)

    with timed(user_id, "usage + value + flags", "code") as info:
        for s in subs:
            s.usage = summarize(signals_for(s, facts, u.checkins.get(s.id, []), today))
            s.value = membership_value(s, facts, today)
            if s.id in u.cancel_pending:
                s.status = "cancel_pending"
            elif s.id in u.kept:
                s.status = "kept"
            s.flags = flag_one(s, u.kept.get(s.id), today)
        flag_overlaps(subs)
        info["note"] = f"{sum(len(s.flags) for s in subs)} flags on {len(subs)} subscriptions"

    u.subscriptions = {s.id: s for s in subs}
    return summary(user_id)


def best_saving(s: Subscription) -> float:
    return max((f.monthly_savings for f in s.flags), default=0.0)


def summary(user_id: str) -> dict:
    subs = list(store.user(user_id).subscriptions.values())
    paying = [s for s in subs if s.status != "trial"]
    return {
        "subscriptions": len(subs),
        "monthly_total": round(sum(s.monthly_cost for s in paying), 2),
        "potential_monthly_savings": round(sum(best_saving(s) for s in subs if s.status != "kept"), 2),
        "flagged": sum(1 for s in subs if any(f.severity != "info" for f in s.flags)),
        "recovered_total": 0.0,
        "recovered_note": "MISSING [cancel-confirmation]: savings aren't confirmed or counted yet.",
    }
