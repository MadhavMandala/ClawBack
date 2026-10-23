"""Annual plans with one charge in the bank window, confirmed by email. Code only.

An annual plan charges once a year, so the 180 days of bank data ClawBack reads usually hold one charge, and one
charge isn't a pattern. It counts as an annual subscription when an email confirms the plan:
  - an Apple or Google Play receipt or subscription email whose plan is yearly ("(Annual)", "Yearly", "/year") and
    whose price fits the charge (equal, or up to 12% more for sales tax), dated from 35 days before the charge (a
    confirmation at the start of a trial) to 5 days after it;
  - an email from the service itself (its sender, or the service named in the subject, is the same merchant as the
    charge) that gives a yearly price ("$69.99/year", "$139 per year", "annual plan ... $96.00") fitting the charge,
    dated up to 400 days before the charge (renewal notices) or 30 days after it (receipts).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Callable

from ..findings.util import day, money
from ..merchants import find_in_text, match_sender, same_merchant
from ..models import Email, StoreReceipt, Transaction

TAX_MAX = 0.12
CENT = 0.01
YEARLY_PLAN = re.compile(r"\((?:annual|yearly|1 year|12 months)\)|\b(?:annual|yearly)\b|/\s*(?:year|yr)\b|per year", re.I)
_AMOUNT = r"\$\s?(\d{1,4}(?:,\d{3})*(?:\.\d{2})?)"
YEARLY_PRICE = re.compile(_AMOUNT + r"\s*(?:/\s*(?:year|yr)\b|per year|a year|each year|annually)|"
                          r"\b(?:annual|yearly)\b[^.$\n]{0,40}?" + _AMOUNT, re.I)


@dataclass
class Hint:
    on: date
    price: float
    store: str | None  # apple | google_play for store mail
    merchant: str | None
    wording: str
    notice: bool = False


def _fits(price: float, charge: float) -> bool:
    return price - CENT <= charge <= price * (1 + TAX_MAX) + CENT


def hints(emails: list[Email], receipts: list[StoreReceipt]) -> list[Hint]:
    out: list[Hint] = []
    for r in receipts:
        for i in r.items:
            if i.price is not None and YEARLY_PLAN.search(f"{i.plan or ''} {i.name}"):
                label = "Apple" if r.store == "apple" else "Google Play"
                kind = "subscription email" if r.kind == "notice" else "receipt"
                out.append(Hint(r.received, i.price, r.store, i.merchant or i.name,
                                f"the {label} {kind} of {day(r.received)}: {i.plan or i.name} at {money(i.price)}",
                                notice=r.kind == "notice"))
    store_ids = {r.email_id for r in receipts}
    for e in emails:
        if e.id in store_ids:
            continue
        text = f"{e.subject}\n{e.body_text}"
        m = YEARLY_PRICE.search(text)
        if not m:
            continue
        sender = match_sender(e.sender)
        named = sender or find_in_text(e.subject)
        if named is None:
            continue
        price = float(next(g for g in m.groups() if g).replace(",", ""))
        out.append(Hint(e.received_at.date(), price, None, named.name,
                        f"the {named.name} email of {day(e.received_at.date())} ({money(price)} a year)"))
    return out


def hint_for(found: list[Hint]) -> Callable[[str, Transaction], str | None]:
    """The annual_hint callback for recurring.detect_series."""
    def check(key: str, t: Transaction) -> str | None:
        kind, _, rest = key.partition(":")
        for h in found:
            if not _fits(h.price, t.amount):
                continue
            days = (t.date - h.on).days  # positive: the email came before the charge
            if kind in ("apple_bill", "google_play"):
                store = "apple" if kind == "apple_bill" else "google_play"
                ok = h.store == store and (-5 <= days <= 35 if h.notice else -5 <= days <= 5)
            elif kind in ("merchant", "bill"):
                ok = h.store is None and same_merchant(h.merchant, rest) and -30 <= days <= 400
            else:
                ok = False
            if ok:
                return (f"One charge in your bank data so far ({money(t.amount)} on {day(t.date)}); {h.wording} "
                        "says it is a yearly plan.")
        return None
    return check
