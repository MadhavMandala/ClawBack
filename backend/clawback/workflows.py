"""The three workflows ClawBack leads with, picked in one place for the dashboard (GET /api/showcase) and the
monthly recap's "next up" (recap.py), so the two always name the same things:

  - a gym you stopped going to (cancelled by email, rules/gyms.json);
  - a streaming service you don't use (its own cancel page);
  - a price drop, or the item being watched when it hasn't dropped.

Each is None when this user has none. The biggest saving wins when there is more than one.
"""

from __future__ import annotations

from . import gyms
from .models import Finding, Subscription
from .pipeline.run import best_saving
from .store import store


def pick(user_id: str) -> dict:
    u = store.user(user_id)
    live = sorted((s for s in u.subscriptions.values() if s.status != "cancelled"), key=lambda s: -best_saving(s))
    demo_ok = u.mode != "real"
    gym: Subscription | None = next((s for s in live if gyms.for_subscription(s, demo=demo_ok)), None)
    streaming: Subscription | None = next(
        (s for s in live if s.category == "video_streaming" and any(f.kind in ("unused", "cancel_pending") for f in s.flags)),
        None)
    drops = [f for f in u.findings.values() if f.kind == "price_drop" and f.status == "open"]
    drop: Finding | None = max(drops, key=lambda f: f.amount, default=None)  # the biggest, so order doesn't matter
    watch = None if drop or not u.price_watch else u.price_watch[0]
    return {"gym": gym, "streaming": streaming, "drop": drop, "watch": watch}
