"""Bills (internet, mobile, insurance, utilities, gyms): price hikes, promo endings, and "you could ask for less".

Data in: recurring charges that match a verified provider in rules/bills.json (pipeline/recurring.py groups them),
plus promo emails ("your promotional rate ends ...").
Rule: bills.json says which providers are usually negotiable and which bills swing month to month (utilities).
Detector, code only:
  - bill_increase: the median of the last 2 charges is at least 10% above the median of the earlier ones.
    High if at least 15%. Savings = the difference.
  - promo_ending: an email says a promotional rate ends on a date that is still ahead (or under a week ago)
    and no increase has shown up yet. Savings = the stated jump, if the email gives both prices.
  - negotiable: an info flag for negotiable providers with nothing else flagged.
  Variable bills (utilities) never get an increase flag from normal month-to-month swings.
Action: actions.negotiate() writes the script. MISSING [bill-market-rates]: competitor offers need Tavily.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from ..models import Email, Flag, Subscription
from .util import day, money

INCREASE = 0.10
HIGH = 0.15
EPS = 1e-9

NEGOTIABLE = {
    "internet": "Internet bills can often be lowered by asking. Want a script?",
    "mobile": "Phone plans can often be lowered by asking or by moving to a cheaper plan. Want a script?",
    "insurance": "Insurance premiums can sometimes be lowered with a re-quote or a discount review. Want a script?",
    "utility": "Some utilities offer budget billing or lower-rate programs if you ask. Want a script?",
    "gym": "Gyms often have cheaper plans, or will freeze a membership, if you ask. Want a script?",
}

_PROMO = re.compile(
    r"promo(?:tional)?\s+(?:rate|price|pricing|offer|discount)\b[^.]{0,60}?\b(?:ends|will end|expires|is ending)",
    re.I)
_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
_MONTH_DATE = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
                         r"(?:,?\s+(\d{4}))?", re.I)
_NUM_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_PRICE = re.compile(r"\$(\d[\d,]*\.\d{2})")


@dataclass
class PromoNotice:
    provider: str
    ends_on: date
    old_price: float | None
    new_price: float | None
    email_date: date


def find_date(text: str, ref: date) -> date | None:
    """First date in the text. A date without a year is the next one on or after `ref` minus a month."""
    m = _MONTH_DATE.search(text)
    n = _NUM_DATE.search(text)
    if n and (not m or n.start() < m.start()):
        try:
            return date(int(n.group(3)), int(n.group(1)), int(n.group(2)))
        except ValueError:
            return None
    if not m:
        return None
    month = _MONTHS.index(m.group(1).lower()[:3]) + 1
    try:
        if m.group(3):
            return date(int(m.group(3)), month, int(m.group(2)))
        found = date(ref.year, month, int(m.group(2)))
        return found if found >= ref - timedelta(days=31) else date(ref.year + 1, month, int(m.group(2)))
    except ValueError:
        return None


def promo_notices(emails: list[Email], bill_provider_for: Callable[[str], dict | None]) -> list[PromoNotice]:
    out: list[PromoNotice] = []
    for e in emails:
        text = f"{e.subject}. {e.body_text}"
        m = _PROMO.search(text)
        if not m:
            continue
        rule = bill_provider_for(f"{e.sender} {e.subject} {e.body_text[:400]}")
        ends = find_date(text[m.start():], e.received_at.date())
        if not rule or not ends:
            continue
        prices = [float(p.replace(",", "")) for p in _PRICE.findall(text)]
        old, new = (prices[0], prices[1]) if len(prices) >= 2 else (None, None)
        out.append(PromoNotice(rule["provider"], ends, old, new, e.received_at.date()))
    return out


def bill_flags(sub: Subscription, amounts: list[float], rule: dict, promos: list[PromoNotice], today: date) -> list[Flag]:
    """`amounts` are this bill's charges, oldest first. `promos` are this provider's promo notices."""
    flags: list[Flag] = []
    ended = sorted((p for p in promos if p.ends_on <= today), key=lambda p: p.ends_on)
    if not rule.get("variable_amount") and len(amounts) >= 3:
        recent, earlier = statistics.median(amounts[-2:]), statistics.median(amounts[:-2])
        rise = (recent - earlier) / earlier if earlier > 0 else 0.0
        if rise >= INCREASE - EPS:
            note = (f" Your promotional rate ended {day(ended[-1].ends_on)} (email of {day(ended[-1].email_date)})."
                    if ended else "")
            flags.append(Flag(
                kind="bill_increase", severity="high" if rise >= HIGH - EPS else "medium",
                message=(f"{sub.merchant} went from {money(earlier)} to {money(recent)} a month (+{rise:.0%}).{note} "
                         "You can ask for the old rate or a new offer."),
                monthly_savings=round(recent - earlier, 2),
            ))
    if not flags:
        upcoming = sorted((p for p in promos if p.ends_on >= today - timedelta(days=7)), key=lambda p: p.ends_on)
        if upcoming:
            p = upcoming[0]
            jump = round(p.new_price - p.old_price, 2) if p.old_price and p.new_price and p.new_price > p.old_price else 0.0
            prices = f": {money(p.old_price)} to {money(p.new_price)} a month" if jump else ""
            flags.append(Flag(
                kind="promo_ending", severity="medium",
                message=f"Your {sub.merchant} promotional rate ends {day(p.ends_on)}{prices}. Ask for a new offer before then.",
                monthly_savings=jump,
            ))
    if not flags and rule.get("negotiable"):
        flags.append(Flag(
            kind="negotiable", severity="info",
            message=NEGOTIABLE.get(rule.get("category"), "This bill can often be lowered by asking. Want a script?"),
        ))
    return flags
