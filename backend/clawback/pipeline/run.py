"""Run the whole pipeline for one user and store the results.

Subscriptions and bills (recurring), then the one-time findings: duplicate charges, bank fees, price drops,
flight refunds and class-action settlements (clawback/findings).
"""

from __future__ import annotations

import re
from datetime import date

from ..findings import rulebook
from ..findings.bills import bill_flags, promo_notices
from ..findings.detect import run_findings
from ..merchants import by_name
from ..models import Cadence, Subscription
from ..store import store
from ..trace import record_repeat, start_run, timed
from .extract import extract_all
from .flags import flag_one, flag_overlaps
from .recurring import detect_series, resolve_store_billed
from .triage import triage
from .usage import signals_for, summarize
from .value import membership_value


def run(user_id: str, today: date | None = None) -> dict:
    today = today or date.today()
    u = store.user(user_id)
    if store.is_cold(user_id):
        # Real mail isn't back in memory yet (store.py, connect.ensure_fresh): a run now would drop every email
        # finding, so the saved results stay until the mail is read again.
        record_repeat(user_id, "pipeline", "code", "skipped", "kept the saved results until the mail is read again")
        return summary(user_id)
    start_run(user_id)  # Nylas / Plaid sync rows and the newest on-click rows stay visible
    rules = rulebook.current()
    bill_for = rules.bill_provider_for if rules else None

    candidates = triage(user_id, u.emails)
    facts = extract_all(user_id, candidates)

    with timed(user_id, "recurring", "code") as info:
        subs, series = detect_series(u.transactions, today, bill_for)
        resolve_store_billed(subs, [(f.merchant, f.amount) for f in facts if f.kind == "store_receipt"])
        n_bills = sum(1 for s in subs if s.kind == "bill")
        info["note"] = (f"{len(u.transactions)} transactions -> {len(subs) - n_bills} subscriptions and {n_bills} bills"
                        + ("" if rules else " (MISSING: no rule data, so bills aren't recognised)"))

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

    promos = promo_notices(u.emails, bill_for) if bill_for else []
    bill_rules = {b["provider"]: b for b in rules.bills} if rules else {}
    u.bill_info = {}
    with timed(user_id, "usage + value + flags", "code") as info:
        for s in subs:
            if s.id in u.cancel_pending:
                s.status = "cancel_pending"
            elif s.id in u.kept:
                s.status = "kept"
            if s.kind == "bill":
                rule = bill_rules.get(s.merchant, {})
                amounts = [t.amount for t in series.get(s.id, [])]
                s.flags = bill_flags(s, amounts, rule, [p for p in promos if p.provider == s.merchant], today)
                u.bill_info[s.id] = {"rule": rule, "amounts": amounts}
                continue
            s.usage = summarize(signals_for(s, facts, u.checkins.get(s.id, []), today))
            s.value = membership_value(s, facts, today)
            s.flags = flag_one(s, u.kept.get(s.id), today)
        flag_overlaps([s for s in subs if s.kind != "bill"])
        info["note"] = f"{sum(len(s.flags) for s in subs)} flags on {len(subs)} subscriptions and bills"

    u.subscriptions = {s.id: s for s in subs}
    u.findings = {f.id: f for f in run_findings(user_id, u, rules, subs, series, today)}
    return summary(user_id)


def best_saving(s: Subscription) -> float:
    return max((f.monthly_savings for f in s.flags), default=0.0)


def summary(user_id: str) -> dict:
    u = store.user(user_id)
    subs = list(u.subscriptions.values())
    paying = [s for s in subs if s.status != "trial"]
    subs_total = round(sum(s.monthly_cost for s in paying if s.kind != "bill"), 2)
    bills_total = round(sum(s.monthly_cost for s in paying if s.kind == "bill"), 2)
    open_findings = [f for f in u.findings.values() if f.status == "open"]
    return {
        "subscriptions": sum(1 for s in subs if s.kind != "bill"),
        "subscriptions_total": subs_total,
        "bills": sum(1 for s in subs if s.kind == "bill"),
        "bills_total": bills_total,
        "monthly_total": round(subs_total + bills_total, 2),
        "potential_monthly_savings": round(sum(best_saving(s) for s in subs if s.status != "kept"), 2),
        "flagged": sum(1 for s in subs if any(f.severity != "info" for f in s.flags)),
        "owed_total": round(sum(f.amount for f in open_findings if f.currency == "USD"), 2),
        "owed_count": len(open_findings),
        "recovered_total": round(sum(u.got_back.values()), 2),
        "recovered_note": ("Self-reported: what you marked as got back. Not checked against your bank yet "
                           "(MISSING [cancel-confirmation])."),
    }
