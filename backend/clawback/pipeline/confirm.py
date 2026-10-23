"""Check that the money came back. Code only; every pipeline run does it, so it happens after every sync.

Cancellations (UserData.cancel_pending, snapshots in UserData.cancellations)
  - The first run after the user starts cancelling keeps a snapshot of the subscription: how its charges are grouped
    (recurring.series_key), the amount, the cadence and the last charge on or before that day.
  - A charge in the same series dated after the day cancelling started means "charged again after you started
    cancelling" (status charged_again, a high flag). A charge on that same day counts as before.
  - No charge by the next expected date (one period after the latest charge seen) plus a grace period (3 days for
    weekly plans, 6 monthly, 10 annual) means confirmed cancelled. The subscription shows as cancelled and leaves the
    monthly totals, and the history gets a dated event with its monthly saving and the charges that didn't come.
  - A confirmed cancellation stays confirmed when old charges roll out of the bank's window. A new charge in the
    series after it was confirmed reopens it as charged_again.
  - Keep (anything that removes the id from cancel_pending) drops the snapshot and its history event.

Refunds for findings marked done (UserData.done_on, snapshots in UserData.refund_watch)
  - Marking a finding done keeps a snapshot (mark_done): detectors rebuild findings every run and drop them once a
    deadline passes, but the refund can arrive later.
  - A matching credit is a negative transaction:
      from the same merchant: its description has the merchant's words (for a bank fee: a refund word such as
        REFUND, REVERSAL, WAIVED or CREDIT plus a fee word; for a settlement: SETTLEMENT plus the defendant's name);
      dated after the original charge, and no earlier than 7 days before the done date (people often mark a
        finding done once they see the money);
      for the finding's amount or the self-reported amount, to the cent. A price-drop refund may add sales tax, so
        up to 12% more counts too. A settlement payout can be any amount.
  - Each credit confirms one finding at most. Findings in EUR or GBP (EU and UK flight compensation) can't be
    matched by amount, so they stay self-reported.

The history itself (totals, events, self-reported amounts) is pipeline/recovered.py.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Callable

from ..findings.util import day, merchant_words, money
from ..models import Cadence, Cancellation, Finding, RecoveryEvent, RefundWatch, Subscription, Transaction
from ..store import UserData
from .recurring import CADENCES, key_matches, series_key

GRACE = {Cadence.weekly: 3, Cadence.monthly: 6, Cadence.annual: 10}
LOOKBACK = timedelta(days=7)
TAX_MAX = 0.12
CENT = 0.01
STOP_WORDS = {"the", "inc", "co", "corp", "corporation", "llc", "ltd", "company", "com", "and", "of", "your", "usa",
              "us", "na", "group"}
REFUND_WORD = re.compile(r"\b(REFUND|REFD|REVERS|REVRSL|RVSL|WAIVE|CREDIT|CR\b|REBATE|REIMB|ADJ)", re.I)
FEE_WORD = re.compile(r"\b(FEE|FEES|CHARGE|CHG|OVERDRAFT|NSF|OD)\b", re.I)


# --- Cancellations ------------------------------------------------------------------------------------

def _period(c: Cadence | None) -> float:
    return CADENCES[c][2] if c else CADENCES[Cadence.monthly][2]


def snapshot(sub: Subscription, started_on: date, txs: list[Transaction],
             key_of: Callable[[Transaction], str]) -> Cancellation:
    before = [t for t in txs if t.date <= started_on]
    key = sub.series_key or (key_of(txs[-1]) if txs else f"merchant:{sub.merchant}")
    return Cancellation(
        subscription_id=sub.id, merchant=sub.merchant, started_on=started_on, series_key=key, amount=sub.amount,
        monthly_cost=sub.monthly_cost, cadence=sub.cadence, category=sub.category, kind=sub.kind,
        billed_by=sub.billed_by, last_charge=before[-1].date if before else None,
        first_due=None if txs else sub.next_expected,
    )


def _evaluate(c: Cancellation, transactions: list[Transaction], next_expected: date | None, today: date,
              bill_for) -> None:
    after = sorted((t for t in transactions if t.amount > 0 and t.date > c.started_on
                    and key_matches(c.series_key, t, bill_for)), key=lambda t: t.date)
    period = _period(c.cadence)
    anchor = after[-1].date if after else c.last_charge
    if anchor is not None:
        due = anchor + timedelta(days=round(period))
    else:
        due = c.first_due or next_expected or c.started_on + timedelta(days=round(period))  # a trial
    c.expected_by = due + timedelta(days=GRACE.get(c.cadence, 6) if c.cadence else 6)
    if after:
        c.charged_again_on, c.charged_again_amount = after[-1].date, after[-1].amount
    if c.status == "confirmed" and after and c.confirmed_on and after[-1].date > c.confirmed_on:
        c.status, c.confirmed_on, c.skipped_charges = "charged_again", None, 0  # billing started again
    if today > c.expected_by:
        if c.status != "confirmed":
            c.status, c.confirmed_on = "confirmed", c.expected_by
        c.skipped_charges = max(1, int((today - due).days // period) + 1)
        extra = (f" It charged once more, on {day(c.charged_again_on)}, after you started cancelling."
                 if c.charged_again_on else "")
        c.note = (f"No charge since {day(anchor)}, and the next one was due around {day(due)}.{extra}" if anchor
                  else f"No charge by {day(due)}, when the first one was due.{extra}")
    elif c.status != "confirmed":
        c.status = "charged_again" if after else "pending"
        c.note = (f"Charged {money(after[-1].amount)} on {day(after[-1].date)}, after you started cancelling on "
                  f"{day(c.started_on)}." if after else f"Waiting for the charge due around {day(due)} not to come.")


def check_cancellations(u: UserData, subs: list[Subscription], stopped: list[Subscription],
                        series: dict[str, list[Transaction]], today: date, bill_for=None) -> list[Subscription]:
    """Update every cancellation snapshot, set each cancelling subscription's status, and return the cancelled ones
    the detector no longer lists (stopped series, or charges rolled out of the bank window) to add back."""
    def key_of(t: Transaction) -> str:
        return series_key(t, bill_for)

    for sid in [s for s in u.cancellations if s not in u.cancel_pending]:
        del u.cancellations[sid]
        u.recovered.pop(f"cancel:{sid}", None)

    active = {s.id: s for s in subs}
    gone = {s.id: s for s in stopped}
    add_back: list[Subscription] = []
    for sid, started in u.cancel_pending.items():
        sub = active.get(sid) or gone.get(sid)
        snap = u.cancellations.get(sid)
        if snap is None or snap.started_on != started:
            if sub is None:
                continue  # nothing known about it yet
            snap = u.cancellations[sid] = snapshot(sub, started, series.get(sid, []), key_of)
        _evaluate(snap, u.transactions, sub.next_expected if sub else None, today, bill_for)
        if sub is None:
            sub = Subscription(
                id=sid, merchant=snap.merchant, category=snap.category, kind=snap.kind, cadence=snap.cadence,
                amount=snap.amount, monthly_cost=snap.monthly_cost, last_charged=snap.last_charge,
                detected_from=["bank"], billed_by=snap.billed_by)
        if sid not in active:
            add_back.append(sub)
        sub.cancellation = snap
        sub.status = "cancelled" if snap.status == "confirmed" else "cancel_pending"
        if snap.status == "confirmed":
            u.recovered[f"cancel:{sid}"] = RecoveryEvent(
                id=f"cancel:{sid}", kind="cancelled_subscription", status="confirmed", on=snap.confirmed_on or today,
                merchant=snap.merchant, amount=round((snap.amount or 0.0) * snap.skipped_charges, 2),
                monthly=snap.monthly_cost, note=snap.note, subscription_id=sid)
        else:
            u.recovered.pop(f"cancel:{sid}", None)
    return add_back


# --- Refunds for done findings ------------------------------------------------------------------------

def _words(name: str) -> list[str]:
    words = [w for w in re.sub(r"[^a-z ]+", " ", (name or "").lower()).split() if w not in STOP_WORDS and len(w) > 1]
    return words[:2]


def _charged_on(f: Finding) -> date | None:
    d = f.details or {}
    raw = None
    if f.kind == "duplicate_charge" and d.get("charges"):
        raw = max(d["charges"])
    elif f.kind == "bank_fee":
        raw = d.get("date")
    elif f.kind == "price_drop":
        raw = d.get("order_date")
    try:
        return date.fromisoformat(raw[:10]) if isinstance(raw, str) else None
    except ValueError:
        return None


def watch_for(f: Finding, got_back: float, done_on: date) -> RefundWatch:
    d = f.details or {}
    if f.kind == "duplicate_charge" and d.get("description"):
        words = merchant_words(d["description"])
    elif f.kind == "bank_fee":
        words = []  # bank wording: matched by refund + fee words instead
    else:
        words = _words(d.get("store") or d.get("airline") or f.merchant)
    return RefundWatch(
        finding_id=f.id, kind=f.kind, category=f.category, merchant=f.merchant, title=f.title, amount=f.amount,
        currency=f.currency, got_back=round(got_back or 0.0, 2), done_on=done_on, charged_on=_charged_on(f),
        match_words=words,
    )


def _description_ok(w: RefundWatch, desc: str) -> bool:
    words = set(re.sub(r"[^a-z ]+", " ", desc.lower()).split())
    if w.kind == "bank_fee":
        return bool(REFUND_WORD.search(desc) and FEE_WORD.search(desc))
    if w.kind == "settlement":
        return "settlement" in words and bool(w.match_words) and w.match_words[0] in words
    return bool(w.match_words) and all(m in words for m in w.match_words)


def _amount_ok(w: RefundWatch, credit: float) -> bool:
    if w.kind == "settlement" and w.amount <= 0 and w.got_back <= 0:
        return credit > 0
    for expected in (w.amount, w.got_back):
        if expected <= 0:
            continue
        if abs(credit - expected) <= CENT + 1e-9:
            return True
        if w.kind == "price_drop" and expected - CENT <= credit <= expected * (1 + TAX_MAX) + CENT:
            return True
    return False


def matching_credit(w: RefundWatch, credits: list[Transaction], used: set[str]) -> Transaction | None:
    if w.currency != "USD":
        return None
    earliest = w.done_on - LOOKBACK
    for t in sorted(credits, key=lambda t: (t.date, t.id)):
        if t.id in used or t.date < earliest or (w.charged_on and t.date <= w.charged_on):
            continue
        if _description_ok(w, t.description) and _amount_ok(w, -t.amount):
            return t
    return None


def mark_done(u: UserData, f: Finding, got_back: float, today: date) -> None:
    """The user marked a finding done: remember when, and what credit to look for on the next sync."""
    u.finding_status[f.id] = f.status = "done"
    u.got_back[f.id] = round(got_back or 0.0, 2)
    u.done_on[f.id] = today
    u.refund_watch[f.id] = watch_for(f, got_back, today)
    u.recovered.pop(f"refund:{f.id}", None)
    if u.mode == "demo":
        from ..demo_data import refund_credit  # noqa: PLC0415 (demo mode only)

        credit = refund_credit(f, today)
        if credit and all(t.id != credit.id for t in u.transactions):
            u.transactions.append(credit)


def check_refunds(u: UserData, today: date) -> int:
    """Look for the credit each done finding waits for. Returns how many are confirmed in all."""
    for fid, status in u.finding_status.items():
        if status == "done" and fid not in u.refund_watch and fid in u.findings:
            u.refund_watch[fid] = watch_for(u.findings[fid], u.got_back.get(fid, 0.0), u.done_on.setdefault(fid, today))
    for fid in [fid for fid in u.refund_watch if u.finding_status.get(fid) != "done"]:
        del u.refund_watch[fid]
        u.recovered.pop(f"refund:{fid}", None)

    credits = [t for t in u.transactions if t.amount < 0]
    used = {w.confirmed_tx for w in u.refund_watch.values() if w.status == "confirmed" and w.confirmed_tx}
    for w in sorted(u.refund_watch.values(), key=lambda w: (w.done_on, w.finding_id)):
        if w.status != "waiting":
            continue
        t = matching_credit(w, credits, used)
        if t is None:
            continue
        used.add(t.id)
        w.status, w.confirmed_on, w.confirmed_amount, w.confirmed_tx = "confirmed", t.date, round(-t.amount, 2), t.id
        w.confirmed_from = f"{day(t.date)}: {t.description.strip()} ({money(-t.amount)} credit)"
    for fid, w in u.refund_watch.items():
        if w.status != "confirmed":
            continue
        u.recovered[f"refund:{fid}"] = RecoveryEvent(
            id=f"refund:{fid}", kind="refund", status="confirmed", on=w.confirmed_on or today, merchant=w.merchant,
            amount=w.confirmed_amount or 0.0, note=f"Matched a bank credit: {w.confirmed_from}", finding_id=fid)
        if f := u.findings.get(fid):
            f.confirmed_amount, f.confirmed_on, f.confirmed_from = w.confirmed_amount, w.confirmed_on, w.confirmed_from
    return sum(1 for w in u.refund_watch.values() if w.status == "confirmed")
