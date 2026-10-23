"""Membership value: does a delivery or shopping membership save more than it costs? Plain arithmetic on receipts.

Covers DashPass, Uber One, Instacart+, Walmart+, Grubhub+ and Amazon Prime, using rules/memberships.json (each
service's published price and the non-member fees a member doesn't pay, with source URLs and check dates).

Per order email from the service in the last 30 days (code reads the subtotal, the delivery or shipping fee, and
any "saved you $X" line; Lightning's saved_amount for that email counts too):
  - The email says what the membership saved: that amount, exactly.
  - Uber rides: the published ride credit (5% of the fare).
  - Under the members' free-delivery minimum: nothing saved (members pay the fee too).
  - A published non-member delivery fee (Instacart+ from $3.99, Walmart+ $7.95 to $9.95): that range. No published
    top end means no upper bound.
  - Shipping memberships (Prime, Walmart+ shipping): an order at or over the non-member free-shipping minimum ($35)
    saved nothing on shipping; under it, the published non-member fee if there is one (Walmart+ $6.99), else the
    shipping charge shown in the email, else unknown.
  - Anything else: unknown (no published fee to estimate from).
Adding these up gives a cautious and a generous total. The verdict is conservative:
  - losing_money (a flag) only when even the generous total is below the fee for the last 30 days. Estimates need
    at least 2 order emails; a receipt that states its own savings is enough on its own.
  - paying_off when the cautious total covers the fee.
  - otherwise too_close, or not_enough_receipts when there are no order emails or nothing can be bounded.
Benefits that aren't delivery or shipping (Prime Video, fuel discounts, included streaming) aren't counted, and the
flag says so. A membership that comes included with another one the user pays for (Grubhub+ with Prime) gets its
own flag (included_elsewhere).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ..findings.util import money
from ..merchants import by_name
from ..models import Email, Flag, MembershipValue, Subscription
from .extract import Fact

PERIOD = timedelta(days=30)
MIN_ESTIMATED = 2  # order emails needed before an estimate (not a stated saving) can raise a flag
RULES_FILE = Path(__file__).resolve().parent.parent / "rules" / "memberships.json"


class Membership(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    service: str
    merchant: str
    monthly_fee: float
    annual_fee: float | None
    order_domains: tuple[str, ...]
    member_free_delivery_min: float | None
    non_member_delivery_fee_low: float | None
    non_member_delivery_fee_high: float | None
    non_member_free_shipping_min: float | None
    non_member_shipping_fee: float | None
    ride_credit_pct: float | None
    included_with: str | None
    not_counted: str
    source_urls: tuple[str, ...]
    checked_on: date
    verified: bool
    notes: str


class MembershipsFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    note: str
    checked_on: date
    memberships: tuple[Membership, ...]


@lru_cache
def memberships() -> dict[str, Membership]:
    data = MembershipsFile.model_validate(json.loads(RULES_FILE.read_text(encoding="utf-8")))
    return {m.key: m for m in data.memberships if m.verified}


def membership_for(sub: Subscription) -> Membership | None:
    m = by_name(sub.merchant)
    return memberships().get(m.membership) if m and m.membership else None


# --- Reading order emails -----------------------------------------------------------------------------

_AMOUNT = r"\$\s?(\d{1,4}(?:,\d{3})*\.\d{2})"
_SAVED = re.compile(r"(?:saved you|you saved|savings?)\b[^$\n]{0,40}?" + _AMOUNT + r"|" + _AMOUNT +
                    r"\s+(?:in )?(?:savings|saved)\b", re.I)
_SUBTOTAL = re.compile(r"(?:item\(?s\)?\s+)?subtotal\b[^$\n]{0,15}?" + _AMOUNT, re.I)
_TOTAL = re.compile(r"(?<![A-Za-z])(?:order total|grand total|total)\b[^$\n]{0,15}?" + _AMOUNT, re.I)
_DELIVERY_FEE = re.compile(r"delivery fee\b[^$\n]{0,15}?" + _AMOUNT, re.I)
_SHIPPING_FEE = re.compile(r"shipping(?: & handling| and handling| fee)?\b[^$\n]{0,15}?" + _AMOUNT, re.I)
_ORDER_ID = re.compile(r"order\s*(?:#|number|no\.?)?\s*:?\s*([0-9]{3}-[0-9]{7}-[0-9]{7}|(?=[A-Z0-9-]*\d)[A-Z0-9-]{6,})", re.I)
_ORDER_WORDS = re.compile(r"\border\b|\breceipt\b|thanks for riding|your trip|delivered|shipped|purchase", re.I)
_RIDE = re.compile(r"thanks for riding|your trip|\bride\b", re.I)
_MEMBERSHIP_MAIL = re.compile(r"membership|renew|subscription|\bplus\b.*\b(?:trial|plan)\b|uber one|dashpass|walmart\+|"
                              r"instacart\+|grubhub\+|prime (?:membership|fee)", re.I)


def _num(m: re.Match | None) -> float | None:
    if not m:
        return None
    raw = next(g for g in m.groups() if g)
    return float(raw.replace(",", ""))


@dataclass
class Order:
    on: date
    subtotal: float | None
    delivery_fee: float | None
    shipping_fee: float | None
    stated: float | None
    ride: bool
    mode: str | None  # delivery | shipping | None
    key: str


def read_order(e: Email, saved_by_model: float | None = None) -> Order | None:
    text = f"{e.subject}\n{e.body_text}"
    if not _ORDER_WORDS.search(text) or _MEMBERSHIP_MAIL.search(e.subject):
        return None
    stated = _num(_SAVED.search(text))
    if stated is None and saved_by_model:
        stated = saved_by_model
    subtotal = _num(_SUBTOTAL.search(text))
    total = _num(_TOTAL.search(text))
    low = text.lower()
    mode = ("shipping" if re.search(r"\bship(?:ped|ping|s)?\b", low) and "delivery from store" not in low
            else "delivery" if "deliver" in low else None)
    oid = _ORDER_ID.search(text)
    return Order(on=e.received_at.date(), subtotal=subtotal if subtotal is not None else total,
                 delivery_fee=_num(_DELIVERY_FEE.search(text)), shipping_fee=_num(_SHIPPING_FEE.search(text)),
                 stated=stated, ride=bool(_RIDE.search(text)) and "order" not in low, mode=mode,
                 key=oid.group(1) if oid else e.id)


def _domain_of(sender: str) -> str:
    return sender.split("@")[-1].lower().strip(" >")


def orders_for(m: Membership, emails: list[Email], facts: list[Fact], today: date) -> list[Order]:
    saved = {f.email_id: f.saved_amount for f in facts if f.saved_amount}
    out: dict[str, Order] = {}
    for e in emails:
        d = _domain_of(e.sender)
        if not any(d == x or d.endswith("." + x) for x in m.order_domains):
            continue
        if not timedelta(0) <= today - e.received_at.date() <= PERIOD:
            continue
        o = read_order(e, saved.get(e.id))
        if o is not None:
            out.setdefault(o.key, o)  # one order, however many emails (confirmed, shipped, delivered)
    return list(out.values())


# --- The arithmetic -----------------------------------------------------------------------------------

def order_saving(m: Membership, o: Order) -> tuple[float, float | None, str]:
    """(cautious, generous or None for no upper bound, basis) for one order."""
    if o.stated is not None:
        return o.stated, o.stated, "stated"
    if o.ride:
        if m.ride_credit_pct and o.subtotal:
            v = round(o.subtotal * m.ride_credit_pct / 100, 2)
            return v, v, "estimated"
        return 0.0, None, "unknown"
    sub = o.subtotal
    if sub is None:
        return 0.0, None, "unknown"
    delivery = m.non_member_delivery_fee_low is not None
    shipping = m.non_member_free_shipping_min is not None

    def delivery_range() -> tuple[float, float | None]:
        if m.member_free_delivery_min and sub < m.member_free_delivery_min:
            return 0.0, 0.0  # under the members' minimum, members pay the delivery fee too
        return m.non_member_delivery_fee_low, m.non_member_delivery_fee_high

    def shipping_range() -> tuple[float, float | None]:
        if sub >= m.non_member_free_shipping_min:
            return 0.0, 0.0  # ships free without the membership too
        fee = m.non_member_shipping_fee or (o.shipping_fee or None)  # else the charge the email shows
        return (fee, fee) if fee is not None else (0.0, None)

    if delivery and (o.mode == "delivery" or not shipping):
        lo, hi = delivery_range()
    elif shipping and (o.mode == "shipping" or not delivery):
        lo, hi = shipping_range()
    elif delivery and shipping:  # Walmart+: can't tell a store delivery from a shipped order
        (lo1, hi1), (lo2, hi2) = delivery_range(), shipping_range()
        lo, hi = min(lo1, lo2), (None if hi1 is None or hi2 is None else max(hi1, hi2))
    elif m.member_free_delivery_min and sub < m.member_free_delivery_min:
        return 0.0, 0.0, "estimated"
    else:
        return 0.0, None, "unknown"  # no published non-member fee to estimate from
    return lo, hi, "estimated"


def membership_value(sub: Subscription, facts: list[Fact], today: date,
                     emails: list[Email] | None = None) -> MembershipValue | None:
    m = membership_for(sub)
    if m is None or sub.amount is None:
        return None
    fee = round(sub.monthly_cost or sub.amount, 2)
    if emails is None:  # facts only (older callers): the orders the extraction read, with what they saved
        orders = [Order(on=f.received, subtotal=f.amount, delivery_fee=None, shipping_fee=None,
                        stated=f.saved_amount, ride=False, mode=None, key=f.email_id)
                  for f in facts if f.merchant == sub.merchant and f.kind == "delivery_order"
                  and today - f.received <= PERIOD]
    else:
        orders = orders_for(m, emails, facts, today)
    source = m.source_urls[0] if m.source_urls else None
    if not orders:
        return MembershipValue(period_fee=fee, uses=0, savings=0.0, net=round(-fee, 2), verdict="not_enough_receipts",
                               basis="none", savings_low=0.0, source_url=source,
                               note=f"No {m.service} order emails in the last 30 days, so there are not enough "
                                    "receipts to tell.")
    parts = [order_saving(m, o) for o in orders]
    low = round(sum(p[0] for p in parts), 2)
    high = None if any(p[1] is None for p in parts) else round(sum(p[1] for p in parts), 2)
    stated = all(p[2] == "stated" for p in parts)
    basis = "stated" if stated else "estimated"
    note = m.not_counted
    if high is not None and high < fee and (stated or len(orders) >= MIN_ESTIMATED):
        verdict, savings = "losing_money", high
        if not stated:
            note = (f"Estimated from {m.service}'s published fees for non-members. " + note).strip()
    elif low >= fee:
        verdict, savings = "paying_off", low
    elif high is None:
        verdict, savings = "not_enough_receipts", low
        note = (f"{len(orders)} {m.service} order email(s), but not enough shown in them to tell what it saved. "
                + note).strip()
    else:
        verdict, savings = "too_close", high
        if not stated and len(orders) < MIN_ESTIMATED:
            verdict = "not_enough_receipts"
            note = (f"Only {len(orders)} {m.service} order email in the last 30 days: not enough receipts to tell. "
                    + note).strip()
    return MembershipValue(period_fee=fee, uses=len(orders), savings=round(savings, 2), net=round(savings - fee, 2),
                           verdict=verdict, basis=basis, savings_low=low, note=note, source_url=source)


def included_elsewhere(subs: list[Subscription]) -> None:
    """Flag a membership the user pays for that another paid membership already includes (Grubhub+ with Prime)."""
    paying: dict[str, Subscription] = {}
    for s in subs:
        if s.status in ("active", "kept") and (mm := membership_for(s)):
            paying[mm.key] = s
    for key, s in paying.items():
        m = memberships()[key]
        if m.included_with and m.included_with in paying:
            other = paying[m.included_with]
            s.flags.append(Flag(
                kind="included_elsewhere", severity="medium",
                message=(f"{other.merchant} includes {m.service} at no extra cost once you link the accounts, and you "
                         f"also pay {money(s.monthly_cost)} a month for it."),
                monthly_savings=s.monthly_cost,
            ))
