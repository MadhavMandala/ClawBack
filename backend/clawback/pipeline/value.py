"""Membership value: does a membership save more than it costs? Plain arithmetic on receipts.

Today this covers delivery memberships (e.g. DashPass), where each order email states what the membership saved.
MISSING: ride-share (Uber One), grocery (Instacart+), shopping (Prime, Walmart+), where savings must be
estimated from order totals and the non-member fee schedule.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..models import MembershipValue, Subscription
from .extract import Fact

PERIOD = timedelta(days=30)


def membership_value(sub: Subscription, facts: list[Fact], today: date) -> MembershipValue | None:
    if sub.category != "delivery_membership" or sub.amount is None:
        return None
    orders = [
        f for f in facts
        if f.merchant == sub.merchant and f.kind == "delivery_order" and today - f.received <= PERIOD
    ]
    savings = round(sum(f.saved_amount or 0.0 for f in orders), 2)
    return MembershipValue(period_fee=sub.amount, uses=len(orders), savings=savings, net=round(savings - sub.amount, 2))
