"""Find recurring charges in bank transactions. Pure code, no model.

A group of charges counts as a subscription when:
  - the charges come at a steady weekly, monthly, quarterly or annual rhythm, and
  - the amount is constant, or changes once and stays changed (a price increase).
Groceries, gas and food orders vary in amount, so they drop out.

Grouping (classify / series_key), first match wins:
  1. a verified bill provider (rules/bills.json, via `bill_for`): kind="bill";
  2. a merchant in rules/merchants.json, by any of its descriptors, so "HBO MAX" and "MAX.COM" stay one series and
     the price step between them shows; its phone, internet and insurance rows are bills too;
  3. set aside, never a subscription (rules/not_subscriptions.json): transfers and card payments, loans and buy now
     pay later, rent and housing, healthcare copays, bank fees (the findings handle those), by Plaid's category
     when the bank gives one, or by description;
  4. the app stores: APPLE.COM/BILL and GOOGLE * charges grouped by exact amount (the bank amount is price plus
     tax, so it repeats exactly). Two apps at one price on different days of the month are split by day;
  5. the first two words of the description once processor prefixes ("SQ *", "TST*", "PAYPAL *") are cut.

One-off charges in a series: when a whole group has no rhythm (an Adobe plan plus one Adobe Stock purchase, a gym's
monthly fee plus its annual fee), the steady run inside it is used: the charges of one amount, or of two amounts
one after the other (a price change). A known merchant needs 2 such charges; an unknown one needs at least 3 and
half of the group, so a coffee shop where one order often costs the same doesn't look like a plan.

Annual plans with one charge in the bank window count when an email confirms the plan (pipeline/annual.py,
passed in as `annual_hint`).

Bills marked variable_amount (utilities) are kept even though the amount swings, and a bill whose price stepped more
than once is still a bill. App-store series come out as "Apple (unmatched)" / "Google Play (unmatched)" and
store_billing.resolve() names them from receipt emails.
"""

from __future__ import annotations

import itertools
import json
import math
import re
import statistics
from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Callable

from ..merchants import APPLE_BILL_PATTERN, GOOGLE_PLAY_PATTERN, by_name, clean_descriptor, match_bank
from ..models import Cadence, PriceChange, Subscription, Transaction

CADENCES = {
    Cadence.weekly: (6, 8, 7),
    Cadence.monthly: (26, 35, 30.44),
    Cadence.quarterly: (85, 97, 91.31),
    Cadence.annual: (350, 380, 365.25),
}
PER_MONTH = {Cadence.weekly: 52 / 12, Cadence.monthly: 1, Cadence.quarterly: 1 / 3, Cadence.annual: 1 / 12}
STORE_KINDS = ("apple_bill", "google_play")
SAME_DAY = 4  # store charges this many days apart in the month count as the same app's day
EXCLUDED_FILE = Path(__file__).resolve().parent.parent / "rules" / "not_subscriptions.json"
PLAID_KIND = {"INCOME": "transfer", "TRANSFER_IN": "transfer", "TRANSFER_OUT": "transfer", "LOAN_PAYMENTS": "loan",
              "MEDICAL": "healthcare", "BANK_FEES": "bank_fee", "RENT_AND_UTILITIES_RENT": "housing"}


@lru_cache
def _excluded() -> tuple[set[str], set[str], list[tuple[str, re.Pattern]]]:
    data = json.loads(EXCLUDED_FILE.read_text(encoding="utf-8"))
    cats = data["plaid_categories"]
    patterns = [(g["kind"], re.compile(p, re.I)) for g in data["groups"] for p in g["patterns"]]
    return set(cats["exclude_primary"]), set(cats["exclude_detailed"]), patterns


def set_aside(t: Transaction) -> str | None:
    """transfer | loan | housing | healthcare | bank_fee when a charge is not a subscription, else None."""
    primary, detailed, patterns = _excluded()
    if t.category:
        if t.category in detailed:
            return PLAID_KIND.get(t.category, "other")
        top = next((p for p in primary if t.category == p or t.category.startswith(p + "_")), None)
        if top:
            return PLAID_KIND.get(top, "other")
    for kind, pattern in patterns:
        if pattern.search(t.description):
            return kind
    from ..rules import fee_kind_for  # noqa: PLC0415 (the rules package is optional data)

    return "bank_fee" if fee_kind_for(t.description) else None


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
    if m is None and (kind := set_aside(t)):
        return f"set_aside:{kind}", None
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


def _fit(txs: list[Transaction], bill: dict | None) -> tuple[Cadence, PriceChange | None] | None:
    if len(txs) < 2:
        return None
    cadence = _cadence([(b.date - a.date).days for a, b in zip(txs, txs[1:])])
    if cadence is None:
        return None
    ok, change, idx = _price_pattern([t.amount for t in txs])
    if bill and (bill.get("variable_amount") or not ok):
        ok, change, idx = True, None, None  # bills may swing (utilities) or step more than once
    if not ok:
        return None
    if change is not None and idx is not None:
        change.changed_on = txs[idx].date
    return cadence, change


def _steady_run(key: str, txs: list[Transaction], bill: dict | None
                ) -> tuple[list[Transaction], Cadence, PriceChange | None] | None:
    """The whole group if it has a rhythm, else the steady run inside it (one-off charges left out)."""
    if fit := _fit(txs, bill):
        return txs, *fit
    if bill and bill.get("variable_amount"):
        return None
    by_amount: dict[float, list[Transaction]] = defaultdict(list)
    for t in txs:
        by_amount[round(t.amount, 2)].append(t)
    clusters = sorted(by_amount.values(), key=lambda c: c[0].date)
    runs = [c for c in clusters if len(c) >= 2]
    runs += [a + b for a, b in itertools.permutations(clusters, 2) if a[-1].date < b[0].date]  # one price step
    known = not key.startswith("raw:")
    need = 2 if known else max(3, math.ceil(len(txs) / 2))
    best = None
    for run in runs:
        run = sorted(run, key=lambda t: t.date)
        if len(run) < need or not (fit := _fit(run, bill)):
            continue
        if best is None or (len(run), run[-1].date) > (len(best[0]), best[0][-1].date):
            best = (run, *fit)
    return best


def detect(transactions: list[Transaction], today: date,
           bill_for: Callable[[str], dict | None] | None = None) -> list[Subscription]:
    return detect_series(transactions, today, bill_for)[0]


def set_aside_count(transactions: list[Transaction], bill_for=None) -> dict[str, int]:
    """How many charges were set aside as not subscriptions, by kind (for the trace)."""
    out: dict[str, int] = defaultdict(int)
    for t in transactions:
        if t.amount > 0 and (key := series_key(t, bill_for)).startswith("set_aside:"):
            out[key.split(":", 1)[1]] += 1
    return dict(out)


def detect_series(transactions: list[Transaction], today: date, bill_for: Callable[[str], dict | None] | None = None,
                  include_stopped: bool = False,
                  annual_hint: Callable[[str, Transaction], str | None] | None = None,
                  ) -> tuple[list[Subscription], dict[str, list[Transaction]]]:
    """Recurring charges, plus each one's charges (oldest first) by subscription id.

    include_stopped: also return series that stopped (no charge for 1.5 periods) with status "stopped", so a
    cancellation can be confirmed. Callers drop the ones they don't need.
    annual_hint(key, charge): for a merchant's only charge in the window, a note when an email confirms an annual
    plan for it (pipeline/annual.py), else None."""
    groups: dict[str, list[Transaction]] = defaultdict(list)
    bills: dict[str, dict] = {}
    for t in transactions:
        if t.amount <= 0:
            continue
        key, rule = classify(t, bill_for)
        if key.startswith("set_aside:"):
            continue
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
        bill = bills.get(key)
        note = None
        if len(txs) == 1:
            note = annual_hint(key, txs[0]) if annual_hint else None
            if note is None or (today - txs[0].date).days > 380:
                continue
            run, cadence, change = txs, Cadence.annual, None
        else:
            found = _steady_run(key, txs, bill)
            if found is None:
                continue
            run, cadence, change = found
        period = CADENCES[cadence][2]
        last = run[-1]
        stopped = (today - last.date).days > period * 1.5  # probably already cancelled
        if stopped and not include_stopped:
            continue
        name, category, billed_by = _name_for(key, bill)
        if key.startswith("merchant:"):
            billed_by = _store_billed(billed_by, name, run)
        typical = statistics.median(t.amount for t in run[-3:]) if bill and bill.get("variable_amount") else last.amount
        sub = Subscription(
            id=re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-"),
            merchant=name,
            category=category,
            kind="bill" if bill else "subscription",
            bill_category=bill.get("category") if bill else None,
            cadence=cadence,
            amount=last.amount,
            monthly_cost=round(typical * PER_MONTH[cadence], 2),
            first_seen=run[0].date,
            last_charged=last.date,
            next_expected=last.date + timedelta(days=round(period)),
            charge_count=len(run),
            price_change=change,
            detected_from=["bank", "email"] if note else ["bank"],
            billed_by=billed_by,
            status="stopped" if stopped else "active",
            series_key=key,
            matched_from=note,
        )
        if key.split(":", 1)[0] in STORE_KINDS and not note:
            store = "Apple" if billed_by == "apple" else "Google Play"
            sub.matched_from = (f"No {store} receipt in your email matches this ${last.amount:.2f} charge yet, so the "
                                f"app is unknown. Your {store} subscriptions page lists what it bills you for.")
        subs.append(sub)
        series[sub.id] = run
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
