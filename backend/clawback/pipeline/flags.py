"""Turn the facts about each subscription into flags the user sees. Pure code, no model."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from ..merchants import OVERLAP_CATEGORIES
from ..models import Flag, Subscription

KEEP_QUIET = timedelta(days=90)  # after "keep", don't nag about usage for 90 days


def _day(d: date) -> str:
    return f"{d:%b} {d.day}"


def cancel_flags(sub: Subscription) -> list[Flag]:
    """What the bank shows since the user started cancelling (pipeline/confirm.py)."""
    c = sub.cancellation
    if c is None:
        return []
    if c.status == "charged_again" and c.charged_again_on:
        return [Flag(
            kind="charged_after_cancel", severity="high",
            message=(f"Charged again after you started cancelling: ${c.charged_again_amount or 0:.2f} on "
                     f"{_day(c.charged_again_on)}. Check that the cancellation went through, and ask "
                     f"{sub.merchant} to refund that charge."),
            monthly_savings=sub.monthly_cost,
        )]
    if c.status == "confirmed":
        since = f" since {_day(c.last_charge)}" if c.last_charge else ""
        return [Flag(
            kind="cancel_confirmed", severity="info",
            message=f"Cancelled: no charge{since}. That's ${c.monthly_cost:.2f} a month you keep.",
        )]
    when = f" after {_day(c.expected_by)}" if c.expected_by else " on the next sync"
    return [Flag(
        kind="cancel_pending", severity="info",
        message=f"You started cancelling on {_day(c.started_on)}. ClawBack checks your bank for a new charge{when}.",
    )]


def flag_one(sub: Subscription, kept_on: date | None, today: date) -> list[Flag]:
    if sub.status == "cancelled":
        return cancel_flags(sub)
    flags: list[Flag] = cancel_flags(sub)
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
        v = sub.value
        if v is not None and v.verdict == "losing_money" and v.net < 0:
            saved = "it saved you" if v.basis == "stated" else "it saved you at most"
            flags.append(Flag(
                kind="membership_losing_money", severity="high" if v.basis == "stated" and not v.note else "medium",
                message=(f"Cost ${v.period_fee:.2f} in the last 30 days. You ordered {v.uses} time(s) and {saved} "
                         f"${v.savings:.2f}. Net: -${-v.net:.2f}." + (f" {v.note}" if v.note else "")),
                monthly_savings=round(-v.net, 2),
            ))
        if (sub.usage.level == "unknown" and sub.status != "trial"
                and (v is None or v.verdict == "not_enough_receipts")):
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
