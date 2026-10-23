"""Run the whole pipeline for one user and store the results.

Subscriptions and bills (recurring), named from the bill and merchant lists, app-store receipts and the naming step;
then the checks that money came back (cancellations and refunds, pipeline/confirm.py); then the one-time findings:
duplicate charges, bank fees, price drops, flight refunds and class-action settlements (clawback/findings).
"""

from __future__ import annotations

import re
from datetime import date

from ..findings import rulebook
from ..findings.bills import bill_flags, promo_notices
from ..findings.detect import run_findings
from ..merchants import by_name, same_merchant
from ..models import Cadence, Subscription
from ..store import store
from ..trace import record, start_run, timed
from . import annual, confirm, recovered, store_billing
from .extract import extract_all
from .flags import cancel_flags, flag_one, flag_overlaps
from .naming import categorize_apps, name_unknown
from .recurring import detect_series, set_aside_count
from .triage import triage
from .usage import keep_holds, reraised_by, signal_trust, signals_for, summarize
from .value import included_elsewhere, membership_value


def run(user_id: str, today: date | None = None) -> dict:
    today = today or date.today()
    u = store.user(user_id)
    start_run(user_id)  # Nylas / Plaid sync rows and the newest on-click rows stay visible
    rules = rulebook.current()
    bill_for = rules.bill_provider_for if rules else None

    candidates = triage(user_id, u.emails)
    facts = extract_all(user_id, candidates)
    receipts = store_billing.read_receipts(user_id, u.emails, facts)

    with timed(user_id, "recurring", "code") as info:
        hint = annual.hint_for(annual.hints(u.emails, receipts))
        found, series = detect_series(u.transactions, today, bill_for, include_stopped=True, annual_hint=hint)
        found = store_billing.resolve(found, series, receipts)
        aside = set_aside_count(u.transactions, bill_for)
        subs = [s for s in found if s.status != "stopped"]
        stopped = [s for s in found if s.status == "stopped"]
        n_bills = sum(1 for s in subs if s.kind == "bill")
        store_named = sum(1 for s in subs if s.billed_by and s.matched_from and s.matched_from.startswith("Matched"))
        unmatched = sum(1 for s in subs if s.merchant.endswith("(unmatched)"))
        info["note"] = (f"{len(u.transactions)} transactions -> {len(subs) - n_bills} subscriptions and {n_bills} bills"
                        + (f"; {store_named} app-store charges named from receipts, {unmatched} unmatched"
                           if store_named or unmatched else "")
                        + (f"; set aside as not subscriptions: "
                           + ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in sorted(aside.items())) if aside else "")
                        + ("" if rules else " (MISSING: no rule data, so bills aren't recognised)"))
    name_unknown(user_id, subs, series)
    categorize_apps(user_id, subs)

    # Email-only: free trials that haven't charged yet.
    known = {s.merchant for s in subs}
    for f in facts:
        if (f.kind == "trial" and f.trial_end and f.trial_end >= today and f.merchant
                and not any(same_merchant(f.merchant, k) for k in known)):
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

    with timed(user_id, "cancellations", "code") as info:
        subs += confirm.check_cancellations(u, subs, stopped, series, today, bill_for)
        states = [c.status for c in u.cancellations.values()]
        info["note"] = (f"{len(u.cancel_pending)} cancelling: {states.count('confirmed')} confirmed, "
                        f"{states.count('charged_again')} charged again, {states.count('pending')} waiting")

    promos = promo_notices(u.emails, bill_for) if bill_for else []
    bill_rules = {b["provider"]: b for b in rules.bills} if rules else {}
    u.bill_info = {}
    trust = signal_trust(subs, facts, u.checkins)
    with timed(user_id, "usage + value + flags", "code") as info:
        for s in subs:
            kept_on = u.kept.get(s.id)
            checkins = u.checkins.get(s.id, [])
            if s.status not in ("cancel_pending", "cancelled") and kept_on and not reraised_by(kept_on, checkins):
                s.status = "kept"
            if s.kind == "bill":
                rule = bill_rules.get(s.merchant, {})
                amounts = [t.amount for t in series.get(s.id, [])]
                s.flags = cancel_flags(s) + ([] if s.status == "cancelled" else
                                             bill_flags(s, amounts, rule, [p for p in promos if p.provider == s.merchant], today))
                u.bill_info[s.id] = {"rule": rule, "amounts": amounts}
                continue
            s.usage = summarize(signals_for(s, facts, checkins, today, trust), checkins, today)
            if no_on := reraised_by(kept_on, checkins):
                s.usage.evidence.insert(0, f"{no_on.isoformat()}: you kept it on {kept_on:%b} {kept_on.day}, "
                                           "then said you didn't use it")
            s.value = membership_value(s, facts, today, u.emails)
            s.flags = flag_one(s, kept_on if keep_holds(kept_on, checkins, today) else None, today)
        flag_overlaps([s for s in subs if s.kind != "bill"])
        included_elsewhere(subs)
        info["note"] = f"{sum(len(s.flags) for s in subs)} flags on {len(subs)} subscriptions and bills"

    u.subscriptions = {s.id: s for s in subs}
    active_series = {s.id: series[s.id] for s in subs if s.id in series}
    u.findings = {f.id: f for f in run_findings(user_id, u, rules, subs, active_series, today)}
    confirmed = confirm.check_refunds(u, today)
    if u.refund_watch:
        waiting = sum(1 for w in u.refund_watch.values() if w.status == "waiting")
        record(user_id, "refund check", "code",
               note=f"{len(u.refund_watch)} findings marked done: {confirmed} refunds confirmed by a bank credit, "
                    f"{waiting} still waiting")
    return summary(user_id)


def best_saving(s: Subscription) -> float:
    return max((f.monthly_savings for f in s.flags), default=0.0)


def summary(user_id: str) -> dict:
    u = store.user(user_id)
    subs = list(u.subscriptions.values())
    paying = [s for s in subs if s.status not in ("trial", "cancelled")]
    subs_total = round(sum(s.monthly_cost for s in paying if s.kind != "bill"), 2)
    bills_total = round(sum(s.monthly_cost for s in paying if s.kind == "bill"), 2)
    open_findings = [f for f in u.findings.values() if f.status == "open"]
    rec = recovered.totals(u)
    return {
        "subscriptions": sum(1 for s in subs if s.kind != "bill" and s.status != "cancelled"),
        "subscriptions_total": subs_total,
        "bills": sum(1 for s in subs if s.kind == "bill" and s.status != "cancelled"),
        "bills_total": bills_total,
        "monthly_total": round(subs_total + bills_total, 2),
        "potential_monthly_savings": round(sum(best_saving(s) for s in subs if s.status not in ("kept", "cancelled")), 2),
        "flagged": sum(1 for s in subs if any(f.severity != "info" for f in s.flags)),
        "owed_total": round(sum(f.amount for f in open_findings if f.currency == "USD"), 2),
        "owed_count": len(open_findings),
        "cancelled": sum(1 for s in subs if s.status == "cancelled"),
        "recovered_total": round(rec["confirmed"] + rec["self_reported"], 2),
        "recovered_confirmed": rec["confirmed"],
        "recovered_self_reported": rec["self_reported"],
        "cancelled_monthly_savings": rec["cancelled_monthly"],
        "recovered_note": recovered.note(rec),
    }

