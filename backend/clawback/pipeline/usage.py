"""Work out whether the user actually uses each subscription.

Bank and email show what you pay, not what you use. Evidence, strongest first:
  1. Per-use receipts (delivery orders, rides): counted, not guessed.
  2. What the user told us in a one-tap check-in ("Used it this month?").
  3. Inactivity emails ("we miss you") and engagement emails ("your top songs").
  4. Nothing at all -> ask the user.

MISSING [usage-learning]: "learning" today means remembering check-in answers and 'keep' decisions.
It does not yet adapt how often it asks, or weigh signals per user.
MISSING [usage-apis] / [browser-extension]: no direct usage data from services or browsing.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..models import Subscription, UsageSignal, UsageSummary
from .extract import Fact

RECENT = timedelta(days=35)
INACTIVITY_WINDOW = timedelta(days=45)


def signals_for(sub: Subscription, facts: list[Fact], checkins: list[tuple[date, bool]], today: date) -> list[UsageSignal]:
    out: list[UsageSignal] = []
    for f in facts:
        if f.merchant != sub.merchant:
            continue
        age = today - f.received
        if f.kind == "delivery_order" and age <= RECENT:
            out.append(UsageSignal(kind="receipt", on=f.received, detail="order receipt", weight=1.0))
        elif f.kind == "engagement" and age <= RECENT:
            out.append(UsageSignal(kind="engagement_email", on=f.received, detail="usage summary email", weight=0.5))
        elif f.kind == "inactivity" and age <= INACTIVITY_WINDOW:
            out.append(UsageSignal(kind="inactivity_email", on=f.received, detail='"we miss you" email', weight=-1.5))
    for on, used in checkins:
        if today - on <= RECENT:
            out.append(UsageSignal(kind="checkin", on=on, detail="you said you used it" if used else "you said you didn't use it", weight=2.0 if used else -2.5))
    return out


def summarize(signals: list[UsageSignal]) -> UsageSummary:
    if not signals:
        return UsageSummary(level="unknown", evidence=["No usage evidence in your email."], needs_checkin=True)
    score = sum(s.weight for s in signals)
    evidence = [f"{s.on.isoformat()}: {s.detail}" for s in sorted(signals, key=lambda s: s.on, reverse=True)]
    said_no = any(s.kind == "checkin" and s.weight < 0 for s in signals)
    if said_no and score < 0:
        return UsageSummary(level="none", evidence=evidence)
    if score < 0:
        return UsageSummary(level="low", evidence=evidence)
    return UsageSummary(level="normal", evidence=evidence)
