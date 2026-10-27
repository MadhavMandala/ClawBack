"""The dashboard donut: what you pay each month in at most six groups, and how much of each you could cut.

Totals match the month sentence in run.summary(): paying items only (no trials, nothing cancelled). The yellow part
of a group is each item's best saving, capped at its cost; kept items cut nothing. Trials about to start get a note
of their own instead of a slice, because you aren't paying for them yet.
"""

from __future__ import annotations

from datetime import date

from ..models import Subscription

MAX_GROUPS = 6
OTHER = "Other"

GROUP_OF: dict[str, str] = {
    "internet": "Home and phone", "mobile": "Home and phone", "utility": "Home and phone",
    "home_security": "Home and phone",
    "insurance": "Insurance",
    "software": "Software and AI", "software_creative": "Software and AI", "ai_assistant": "Software and AI",
    "security_vpn": "Software and AI",
    "video_streaming": "Streaming", "music": "Streaming",
    "cloud_storage": "Cloud storage",
    "delivery_membership": "Food delivery", "meal_kit": "Food delivery",
    "fitness": "Gym and fitness",
}


def could_cut(s: Subscription) -> float:
    if s.status == "kept":
        return 0.0
    best = max((f.monthly_savings for f in s.flags), default=0.0)
    return round(max(0.0, min(best, s.monthly_cost)), 2)


def _group(label: str, items: list[Subscription]) -> dict:
    items = sorted(items, key=lambda s: -s.monthly_cost)
    return {
        "label": label,
        "monthly": round(sum(s.monthly_cost for s in items), 2),
        "could_cut": round(sum(could_cut(s) for s in items), 2),
        "items": [{"id": s.id, "merchant": s.merchant, "monthly": round(s.monthly_cost, 2), "could_cut": could_cut(s)}
                  for s in items],
    }


def spend_groups(subs: list[Subscription]) -> list[dict]:
    paying = [s for s in subs if s.status not in ("trial", "cancelled") and s.monthly_cost > 0]
    by_label: dict[str, list[Subscription]] = {}
    for s in paying:
        by_label.setdefault(GROUP_OF.get(s.category, OTHER), []).append(s)
    total = lambda items: sum(s.monthly_cost for s in items)  # noqa: E731
    named = sorted(((k, v) for k, v in by_label.items() if k != OTHER), key=lambda kv: -total(kv[1]))
    other = by_label.get(OTHER, [])
    limit = MAX_GROUPS - (1 if other or len(named) > MAX_GROUPS else 0)
    for _, items in named[limit:]:
        other = other + items
    groups = [_group(k, v) for k, v in named[:limit]]
    if other:
        groups.append(_group(OTHER, other))
    return groups


def trial_notes(subs: list[Subscription], today: date) -> list[dict]:
    return [
        {"id": s.id, "merchant": s.merchant, "amount": round(s.monthly_cost, 2), "starts_on": s.next_expected.isoformat()}
        for s in sorted(subs, key=lambda s: s.next_expected or date.max)
        if s.status == "trial" and s.next_expected and s.next_expected >= today and s.monthly_cost > 0
    ]
