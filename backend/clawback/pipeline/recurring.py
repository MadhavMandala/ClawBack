"""Find recurring charges in bank transactions. Pure code, no model.

A group of charges counts as a subscription when:
  - the charges come at a steady weekly, monthly or annual rhythm, and
  - the amount is constant, or changes once and stays changed (a price increase).
Groceries, gas and food orders vary in amount, so they drop out.

MISSING [app-store-resolution]: APPLE.COM/BILL and GOOGLE * charges are grouped by amount and named only when
an Apple / Google Play receipt email with the same amount is found (see resolve_store_billed).
MISSING: an annual plan needs two charges to be detected from bank data, so in the first year it shows up only
through renewal emails.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from datetime import date, timedelta

from ..merchants import APPLE_BILL_PATTERN, GOOGLE_PLAY_PATTERN, by_name, match_bank
from ..models import Cadence, PriceChange, Subscription, Transaction

CADENCES = {
    Cadence.weekly: (6, 8, 7),
    Cadence.monthly: (26, 35, 30.44),
    Cadence.annual: (350, 380, 365.25),
}


def group_key(t: Transaction) -> str:
    if m := match_bank(t.description):
        return f"merchant:{m.name}"
    if APPLE_BILL_PATTERN.search(t.description):
        return f"apple_bill:{t.amount:.2f}"
    if GOOGLE_PLAY_PATTERN.search(t.description):
        return f"google_play:{t.amount:.2f}"
    words = re.sub(r"[^a-z ]+", " ", t.description.lower()).split()
    return "raw:" + " ".join(words[:2])


def _cadence(gaps: list[int]) -> Cadence | None:
    med = statistics.median(gaps)
    for cad, (lo, hi, _) in CADENCES.items():
        if lo <= med <= hi and all(lo - 3 <= g <= hi + 3 for g in gaps):
            return cad
    return None


def _price_pattern(amounts: list[float]) -> tuple[bool, PriceChange | None, int | None]:
    """Constant, or exactly one lasting change. Returns (ok, change, index_of_change)."""
    rounded = [round(a, 2) for a in amounts]
    changes = [i for i in range(1, len(rounded)) if rounded[i] != rounded[i - 1]]
    if not changes:
        return True, None, None
    if len(changes) == 1:
        i = changes[0]
        return True, PriceChange(old_amount=rounded[i - 1], new_amount=rounded[i], changed_on=date.min), i
    return False, None, None


def detect(transactions: list[Transaction], today: date) -> list[Subscription]:
    groups: dict[str, list[Transaction]] = defaultdict(list)
    for t in transactions:
        if t.amount > 0:
            groups[group_key(t)].append(t)

    subs: list[Subscription] = []
    for key, txs in groups.items():
        txs.sort(key=lambda t: t.date)
        if len(txs) < 2:
            continue
        gaps = [(b.date - a.date).days for a, b in zip(txs, txs[1:])]
        cadence = _cadence(gaps)
        if cadence is None:
            continue
        ok, change, idx = _price_pattern([t.amount for t in txs])
        if not ok:
            continue
        if change is not None and idx is not None:
            change.changed_on = txs[idx].date
        period = CADENCES[cadence][2]
        last = txs[-1]
        if (today - last.date).days > period * 1.5:
            continue  # stopped: probably already cancelled
        name, category = _name_for(key)
        monthly = last.amount * {Cadence.weekly: 52 / 12, Cadence.monthly: 1, Cadence.annual: 1 / 12}[cadence]
        subs.append(
            Subscription(
                id=re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-"),
                merchant=name,
                category=category,
                cadence=cadence,
                amount=last.amount,
                monthly_cost=round(monthly, 2),
                first_seen=txs[0].date,
                last_charged=last.date,
                next_expected=last.date + timedelta(days=round(period)),
                charge_count=len(txs),
                price_change=change,
                detected_from=["bank"],
            )
        )
    return subs


def _name_for(key: str) -> tuple[str, str]:
    kind, _, rest = key.partition(":")
    if kind == "merchant":
        m = by_name(rest)
        return rest, (m.category if m else "unknown")
    if kind == "apple_bill":
        return f"Apple subscription (${rest}, app unknown)", "unknown"
    if kind == "google_play":
        return f"Google Play subscription (${rest}, app unknown)", "unknown"
    return rest.title(), "unknown"


def resolve_store_billed(subs: list[Subscription], store_receipts: list[tuple[str | None, float | None]]) -> None:
    """Name APPLE.COM/BILL-style subscriptions from receipt emails with the same amount."""
    for s in subs:
        if not s.merchant.startswith(("Apple subscription", "Google Play subscription")):
            continue
        for merchant_name, amount in store_receipts:
            if merchant_name and amount is not None and s.amount is not None and abs(amount - s.amount) < 0.005:
                m = by_name(merchant_name)
                s.merchant = merchant_name
                s.category = m.category if m else s.category
                s.id = re.sub(r"[^a-z0-9]+", "-", merchant_name.lower()).strip("-")
                s.detected_from.append("email")
                break
