"""Find recurring charges in bank transactions. Pure code, no model.

A group of charges counts as a subscription when:
  - the charges come at a steady weekly, monthly or annual rhythm, and
  - the amount is constant, or changes once and stays changed (a price increase).
Groceries, gas and food orders vary in amount, so they drop out.

Grouping (series_key): a verified bill provider (rules/bills.json, via `bill_for`) first, then a merchant from
rules/merchants.json, then the app stores, then the first two words of the description once processor prefixes
("SQ *", "TST*", "PAYPAL *") are cut.

Bills: charges that match a verified provider are grouped by provider and come out with kind="bill". Bills marked
variable_amount (utilities) are kept even though the amount swings, and a bill whose price stepped more than once is
still a bill.

App stores: APPLE.COM/BILL and GOOGLE * charges are grouped by exact amount (the bank amount is price plus tax, so
it repeats exactly). Two apps at the same price on different days of the month are split by day of the month.
They come out as "Apple (unmatched)" / "Google Play (unmatched)" and store_billing.resolve() names them from
receipt emails.

MISSING: an annual plan needs two charges to be detected from bank data, so in the first year it shows up only
through renewal emails.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import Callable

from ..merchants import APPLE_BILL_PATTERN, GOOGLE_PLAY_PATTERN, by_name, clean_descriptor, match_bank
from ..models import Cadence, PriceChange, Subscription, Transaction

CADENCES = {
    Cadence.weekly: (6, 8, 7),
    Cadence.monthly: (26, 35, 30.44),
    Cadence.annual: (350, 380, 365.25),
}
STORE_KINDS = ("apple_bill", "google_play")
SAME_DAY = 4  # store charges this many days apart in the month count as the same app's day


def group_key(t: Transaction) -> str:
    if m := match_bank(t.description):
        return f"merchant:{m.name}"
    if APPLE_BILL_PATTERN.search(t.description):
        return f"apple_bill:{t.amount:.2f}"
    if GOOGLE_PLAY_PATTERN.search(t.description):
        return f"google_play:{t.amount:.2f}"
    words = re.sub(r"[^a-z ]+", " ", clean_descriptor(t.description).lower()).split()
    return "raw:" + " ".join(words[:2])


def classify(t: Transaction, bill_for: Callable[[str], dict | None] | None = None) -> tuple[str, dict | None]:
    """(group key, bill rule or None). Verified providers in rules/bills.json win; a bill in the merchant list
    (a phone, internet or insurance company bills.json doesn't cover) gets a plain rule with no pages."""
    rule = bill_for(t.description) if bill_for else None
    if rule:
        return f"bill:{rule['provider']}", rule
    m = match_bank(t.description)
    if m and m.bill:
        return f"bill:{m.name}", {"provider": m.name, "category": m.category, "negotiable": False,
                                  "variable_amount": False, "from_merchant_list": True}
    return group_key(t), None


def series_key(t: Transaction, bill_for: Callable[[str], dict | None] | None = None) -> str:
    """The group a charge belongs to, as detect_series groups it."""
    return classify(t, bill_for)[0]


def _store_billed(m_billed_by: str | None, name: str, txs: list[Transaction]) -> str | None:
    """A known app whose charges read "GOOGLE *<app>" is billed through Google Play (Google's own services aren't)."""
    if m_billed_by:
        return m_billed_by
    m = by_name(name)
    own = m is not None and any(d in ("google.com", "youtube.com") for d in m.sender_domains)
    if not own and txs and all(GOOGLE_PLAY_PATTERN.search(t.description) for t in txs[-2:]):
        return "google_play"
    return None


def _day_gap(a: int, b: int) -> int:
    d = abs(a - b) % 31
    return min(d, 31 - d)


def key_matches(key: str, t: Transaction, bill_for: Callable[[str], dict | None] | None = None) -> bool:
    """Does a charge belong to a series key? Store series split by day ("apple_bill:9.99@11") also check the day."""
    base, _, day = key.partition("@")
    if series_key(t, bill_for) != base:
        return False
    return not day or _day_gap(t.date.day, int(day)) <= SAME_DAY


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


def _split_by_day(key: str, txs: list[Transaction]) -> dict[str, list[Transaction]]:
    """Same-amount store charges on different days of the month: one group per day (two apps at one price)."""
    clusters: list[list[Transaction]] = []
    for t in txs:
        home = next((c for c in clusters if _day_gap(c[0].date.day, t.date.day) <= SAME_DAY), None)
        if home is None:
            clusters.append([t])
        else:
            home.append(t)
    return {f"{key}@{c[0].date.day}": c for c in clusters}


def detect(transactions: list[Transaction], today: date,
           bill_for: Callable[[str], dict | None] | None = None) -> list[Subscription]:
    return detect_series(transactions, today, bill_for)[0]


def detect_series(transactions: list[Transaction], today: date, bill_for: Callable[[str], dict | None] | None = None,
                  include_stopped: bool = False) -> tuple[list[Subscription], dict[str, list[Transaction]]]:
    """Recurring charges, plus each one's charges (oldest first) by subscription id.

    include_stopped: also return series that stopped (no charge for 1.5 periods) with status "stopped", so a
    cancellation can be confirmed. Callers drop the ones they don't need."""
    groups: dict[str, list[Transaction]] = defaultdict(list)
    bills: dict[str, dict] = {}
    for t in transactions:
        if t.amount <= 0:
            continue
        key, rule = classify(t, bill_for)
        if rule:
            bills[key] = rule
        groups[key].append(t)

    for key in [k for k in groups if k.split(":", 1)[0] in STORE_KINDS]:
        txs = sorted(groups[key], key=lambda t: t.date)
        gaps = [(b.date - a.date).days for a, b in zip(txs, txs[1:])]
        if len(txs) >= 4 and _cadence(gaps) is None:
            parts = _split_by_day(key, txs)
            if len(parts) > 1:
                del groups[key]
                groups.update(parts)

    subs: list[Subscription] = []
    series: dict[str, list[Transaction]] = {}
    for key, txs in groups.items():
        txs.sort(key=lambda t: t.date)
        if len(txs) < 2:
            continue
        gaps = [(b.date - a.date).days for a, b in zip(txs, txs[1:])]
        cadence = _cadence(gaps)
        if cadence is None:
            continue
        bill = bills.get(key)
        ok, change, idx = _price_pattern([t.amount for t in txs])
        if bill and (bill.get("variable_amount") or not ok):
            ok, change, idx = True, None, None  # bills may swing (utilities) or step more than once
        if not ok:
            continue
        if change is not None and idx is not None:
            change.changed_on = txs[idx].date
        period = CADENCES[cadence][2]
        last = txs[-1]
        stopped = (today - last.date).days > period * 1.5  # probably already cancelled
        if stopped and not include_stopped:
            continue
        name, category, billed_by = _name_for(key, bill)
        if key.startswith("merchant:"):
            billed_by = _store_billed(billed_by, name, txs)
        per_month = {Cadence.weekly: 52 / 12, Cadence.monthly: 1, Cadence.annual: 1 / 12}[cadence]
        typical = statistics.median(t.amount for t in txs[-3:]) if bill and bill.get("variable_amount") else last.amount
        sub = Subscription(
            id=re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-"),
            merchant=name,
            category=category,
            kind="bill" if bill else "subscription",
            bill_category=bill.get("category") if bill else None,
            cadence=cadence,
            amount=last.amount,
            monthly_cost=round(typical * per_month, 2),
            first_seen=txs[0].date,
            last_charged=last.date,
            next_expected=last.date + timedelta(days=round(period)),
            charge_count=len(txs),
            price_change=change,
            detected_from=["bank"],
            billed_by=billed_by,
            status="stopped" if stopped else "active",
            series_key=key,
        )
        if key.split(":", 1)[0] in STORE_KINDS:
            store = "Apple" if billed_by == "apple" else "Google Play"
            sub.matched_from = (f"No {store} receipt in your email matches this ${last.amount:.2f} charge yet, so the "
                                f"app is unknown. Your {store} subscriptions page lists what it bills you for.")
        subs.append(sub)
        series[sub.id] = txs
    return subs, series


def _name_for(key: str, bill: dict | None = None) -> tuple[str, str, str | None]:
    """(merchant name, category, billed_by) for a group key."""
    kind, _, rest = key.partition(":")
    if kind == "bill" and bill:
        return bill["provider"], bill.get("category") or "bill", None
    if kind == "merchant":
        m = by_name(rest)
        return rest, (m.category if m else "unknown"), (m.billed_by if m else None)
    if kind == "apple_bill":
        return "Apple (unmatched)", "unknown", "apple"
    if kind == "google_play":
        return "Google Play (unmatched)", "unknown", "google_play"
    return rest.title(), "unknown", None
