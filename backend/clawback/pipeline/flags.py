"""Turn the facts about each subscription into flags the user sees. Pure code, no model."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from ..merchants import OVERLAP_CATEGORIES
from ..models import Flag, Subscription

KEEP_QUIET = timedelta(days=90)  # after "keep", don't nag about usage for 90 days


def flag_one(sub: Subscription, kept_on: date | None, today: date) -> list[Flag]:
    flags: list[Flag] = []
    quiet = kept_on is not None and today - kept_on < KEEP_QUIET

    if sub.status == "trial" and sub.next_expected:
        days = (sub.next_expected - today).days
        when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
        flags.append(Flag(
            kind="trial_ending", severity="high",
            message=f"Free trial ends {sub.next_expected:%b %d} ({when}). Then ${sub.amount:.2f}/month.",
            monthly_savings=sub.monthly_cost,
        ))

    if not quiet:
        if sub.usage.level in ("none", "low"):
            flags.append(Flag(
                kind="unused", severity="high",
                message=f"Looks unused ({sub.usage.evidence[0].split(': ', 1)[-1]}). It costs ${sub.monthly_cost:.2f}/month.",
                monthly_savings=sub.monthly_cost,
            ))
        if sub.value is not None and sub.value.net < 0:
            v = sub.value
            flags.append(Flag(
                kind="membership_losing_money", severity="high",
                message=(f"Cost ${v.period_fee:.2f} in the last 30 days. You ordered {v.uses} time(s) and it saved "
                         f"you ${v.savings:.2f}. Net: -${-v.net:.2f}."),
                monthly_savings=round(-v.net, 2),
            ))
        if sub.usage.level == "unknown" and sub.status != "trial" and sub.value is None:
            flags.append(Flag(
                kind="unknown_usage", severity="info",
                message=f"No sign of use in your email. Did you use {sub.merchant} this month?",
            ))

    if sub.price_change and sub.price_change.new_amount > sub.price_change.old_amount:
        pc = sub.price_change
        flags.append(Flag(
            kind="price_increase", severity="medium",
            message=(f"Price went from ${pc.old_amount:.2f} to ${pc.new_amount:.2f} on {pc.changed_on:%b %d} "
                     f"(+${pc.new_amount - pc.old_amount:.2f}/month). MISSING: state-law refund check."),
            monthly_savings=0.0,
        ))
    return flags


def flag_overlaps(subs: list[Subscription]) -> None:
    by_cat: dict[str, list[Subscription]] = defaultdict(list)
    for s in subs:
        if s.status in ("active", "kept") and s.category in OVERLAP_CATEGORIES:
            by_cat[s.category].append(s)
    for cat, group in by_cat.items():
        if len(group) < 2:
            continue
        names = " and ".join(s.merchant for s in group)
        total = sum(s.monthly_cost for s in group)
        cheapest = min(s.monthly_cost for s in group)
        for s in group:
            s.flags.append(Flag(
                kind="overlap", severity="medium",
                message=(f"You pay for {names} ({cat.replace('_', ' ')}), ${total:.2f}/month together. "
                         f"Keeping one saves at least ${cheapest:.2f}/month."),
                monthly_savings=cheapest if s.monthly_cost == cheapest else 0.0,
            ))
