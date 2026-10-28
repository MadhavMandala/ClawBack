"""What the Gmail add-on shows: one flag per merchant that has money in it, with the sender domains its emails come
from. The extension matches those domains against inbox rows inside the browser, so nothing from Gmail reaches the
server. A flag carries no email text: only the merchant, lines ClawBack wrote, an amount and a dashboard link.

The demo connects Gmail for sending only, so ClawBack has no Gmail message ids to match on. Matching by sender
domain works for the demo month and for a real inbox alike.
"""

from __future__ import annotations

from ..config import settings
from ..merchants import by_name
from ..models import Finding, Subscription
from ..store import store
from .run import best_saving

# Stores and airlines behind one-time findings. merchants.json lists subscriptions only.
FINDING_DOMAINS = {
    "Best Buy": ("bestbuy.com",),
    "Staples": ("staples.com",),
    "Target": ("target.com",),
    "Walmart": ("walmart.com",),
    "Amazon": ("amazon.com",),
    "United": ("united.com",),
    "Delta": ("delta.com",),
    "American Airlines": ("aa.com",),
}
FINDING_KINDS = ("price_drop", "duplicate_charge", "flight_refund", "flight_compensation")
SKIP_STATUS = ("kept", "cancel_pending", "cancelled")


def _link(target: str) -> str:
    return f"{settings.frontend_origins[0]}/dashboard?focus={target}"


def _sub_flag(s: Subscription) -> dict | None:
    saving = best_saving(s)
    m = by_name(s.merchant)
    if saving <= 0 or s.status in SKIP_STATUS or m is None or not m.sender_domains:
        return None
    lines = [f.message for f in sorted(s.flags, key=lambda f: -f.monthly_savings) if f.message][:2]
    return {"target": f"sub:{s.id}", "merchant": s.merchant, "domains": list(m.sender_domains), "lines": lines,
            "amount": round(saving, 2), "period": "month", "link": _link(f"sub:{s.id}")}


def _finding_flag(f: Finding) -> dict | None:
    domains = FINDING_DOMAINS.get(f.merchant)
    if f.status != "open" or f.kind not in FINDING_KINDS or f.amount <= 0 or not domains:
        return None
    return {"target": f"finding:{f.id}", "merchant": f.merchant, "domains": list(domains), "lines": [f.title],
            "amount": round(f.amount, 2), "period": "once", "link": _link(f"finding:{f.id}")}


def email_flags(user_id: str) -> list[dict]:
    """Flags, biggest amount first. When two flags share a domain the extension shows the first."""
    u = store.user(user_id)
    out = [x for x in (*map(_sub_flag, u.subscriptions.values()), *map(_finding_flag, u.findings.values())) if x]
    return sorted(out, key=lambda x: -x["amount"])
